"""
Dependency injection factory untuk Phase 2 AI services.
"""
from fastapi import Depends
from sqlalchemy.orm import Session

from app.ai.memory.conversation_memory import ConversationMemory
from app.ai.orchestrator.ai_orchestrator import AIOrchestrator
from app.ai.providers.base import ProviderName
from app.ai.providers.ollama_provider import OllamaProvider
from app.ai.providers.openai_provider import OpenAIProvider
from app.ai.providers.claude_provider import ClaudeProvider
from app.ai.providers.gemini_provider import GeminiProvider
from app.ai.providers.openrouter_provider import OpenRouterProvider
from app.ai.providers.groq_provider import GroqProvider
from app.ai.router.llm_router import LLMRouter
from app.db.database import get_db
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.message_repository import MessageRepository
from app.repositories.provider_log_repository import ProviderLogRepository

# ── Singleton router — dibuat sekali, is_available() baca env fresh ──────────
_router: LLMRouter | None = None


def _get_router() -> LLMRouter:
    global _router
    if _router is None:
        providers = {
            ProviderName.OLLAMA:      OllamaProvider(),
            ProviderName.OPENAI:      OpenAIProvider(),
            ProviderName.CLAUDE:      ClaudeProvider(),
            ProviderName.GEMINI:      GeminiProvider(),
            ProviderName.OPENROUTER:  OpenRouterProvider(),
            ProviderName.GROQ:        GroqProvider(),
        }
        _router = LLMRouter(providers=providers)
    return _router


def get_orchestrator(
    db: Session = Depends(get_db),
) -> AIOrchestrator:
    message_repo = MessageRepository(db)
    conv_repo    = ConversationRepository(db)
    log_repo     = ProviderLogRepository(db)
    memory       = ConversationMemory(message_repo)
    router       = _get_router()

    return AIOrchestrator(
        router=router,
        memory=memory,
        conversation_repo=conv_repo,
        message_repo=message_repo,
        provider_log_repo=log_repo,
)