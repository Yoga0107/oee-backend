"""
AI Orchestrator — koordinator pusat Phase 2.
Sync version — kompatibel dengan SessionLocal dari app/db/database.py
"""
from __future__ import annotations

import logging
import uuid
from typing import Optional

from app.ai.memory.conversation_memory import ConversationMemory
from app.ai.providers.base import GenerationResult, ProviderName
from app.ai.router.llm_router import LLMRouter, RoutingDecision
from app.ai.token.estimator import estimate_tokens
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.message_repository import MessageRepository
from app.repositories.provider_log_repository import ProviderLogRepository

logger = logging.getLogger(__name__)

_MAX_RETRIES = 2


class OrchestratorResult:
    def __init__(
        self,
        content: str,
        provider: ProviderName,
        model: str,
        conversation_id: str,
        routing_reason: str,
        total_tokens: int,
        cost_usd: float,
    ):
        self.content = content
        self.provider = provider
        self.model = model
        self.conversation_id = conversation_id
        self.routing_reason = routing_reason
        self.total_tokens = total_tokens
        self.cost_usd = cost_usd


class AIOrchestrator:
    """Koordinator: routing → memory → generate → persist."""

    def __init__(
        self,
        router: LLMRouter,
        memory: ConversationMemory,
        conversation_repo: ConversationRepository,
        message_repo: MessageRepository,
        provider_log_repo: ProviderLogRepository,
    ):
        self._router = router
        self._memory = memory
        self._conversation_repo = conversation_repo
        self._message_repo = message_repo
        self._provider_log_repo = provider_log_repo

    async def chat(
        self,
        user_message: str,
        conversation_id: Optional[str],
        user_id: Optional[str] = None,
        has_image: bool = False,
        force_provider: Optional[ProviderName] = None,
    ) -> OrchestratorResult:

        # 1. Pastikan conversation ada di DB
        #    - Jika conversation_id tidak dikirim → buat baru
        #    - Jika conversation_id dikirim tapi tidak ada di DB (misal rollback
        #      di request sebelumnya) → buat ulang dengan ID yang sama agar
        #      foreign key ai_messages tetap valid
        if not conversation_id:
            conversation_id = str(uuid.uuid4())
            logger.info("Orchestrator: creating new conversation id=%s", conversation_id)
            self._conversation_repo.create(
                conversation_id=conversation_id,
                user_id=user_id,
                title=user_message[:80],
            )
        else:
            existing = self._conversation_repo.get(conversation_id)
            if not existing:
                logger.warning(
                    "Orchestrator: conversation_id=%s not found in DB, re-creating.",
                    conversation_id,
                )
                self._conversation_repo.create(
                    conversation_id=conversation_id,
                    user_id=user_id,
                    title=user_message[:80],
                )

        # 2. Simpan pesan user ke DB
        self._message_repo.save(
            conversation_id=conversation_id,
            role="user",
            content=user_message,
        )

        # 3. Ambil history dan build prompt
        history = self._memory.get_context(conversation_id)
        prompt_with_history = self._memory.format_prompt(history, user_message)

        # 4. Routing
        if force_provider:
            decision = RoutingDecision(
                provider_name=force_provider,
                reason="manual_override",  # type: ignore[arg-type]
                estimated_tokens=estimate_tokens(prompt_with_history),
                fallback_chain=self._router._build_fallback_chain(force_provider),
            )
        else:
            decision = self._router.route(user_message, has_image=has_image)

        # 5. Generate dengan retry + fallback
        result = await self._generate_with_fallback(prompt_with_history, decision)

        # 6. Simpan response AI
        self._message_repo.save(
            conversation_id=conversation_id,
            role="assistant",
            content=result.content,
            provider=result.provider.value,
            model=result.model,
            total_tokens=result.total_tokens,
        )

        # 7. Simpan provider log
        self._provider_log_repo.log(
            conversation_id=conversation_id,
            provider=result.provider.value,
            model=result.model,
            prompt_tokens=result.prompt_tokens,
            completion_tokens=result.completion_tokens,
            total_tokens=result.total_tokens,
            cost_usd=result.cost_usd,
            routing_reason=str(decision.reason),
        )

        return OrchestratorResult(
            content=result.content,
            provider=result.provider,
            model=result.model,
            conversation_id=conversation_id,
            routing_reason=str(decision.reason),
            total_tokens=result.total_tokens,
            cost_usd=result.cost_usd,
        )

    async def _generate_with_fallback(
        self,
        prompt: str,
        decision: RoutingDecision,
    ) -> GenerationResult:
        """Coba provider utama, lalu fallback jika gagal."""
        candidates = [decision.provider_name] + decision.fallback_chain

        for provider_name in candidates:
            provider = self._router.get_provider(provider_name)
            if not provider.is_available:
                continue

            for attempt in range(1, _MAX_RETRIES + 1):
                try:
                    logger.info("Orchestrator: provider=%s attempt=%d", provider_name, attempt)
                    result = await provider.generate(prompt)
                    return result
                except Exception as exc:
                    logger.warning("Provider %s attempt %d failed: %s", provider_name, attempt, exc)
                    if attempt == _MAX_RETRIES:
                        logger.error("Provider %s exhausted retries.", provider_name)

        raise RuntimeError("Semua LLM provider gagal. Silakan coba lagi.")