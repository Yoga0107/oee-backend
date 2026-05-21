import os
from typing import AsyncIterator, Optional

from app.ai.providers.base import (
    BaseLLMProvider,
    GenerationResult,
    ProviderName,
    ProviderTier,
)
from app.ai.token.estimator import estimate_tokens

_INPUT_COST_PER_1K = 0.0   # gemini-2.0-flash-exp = free
_OUTPUT_COST_PER_1K = 0.0


class GeminiProvider(BaseLLMProvider):
    """Google Gemini provider — free tier via gemini-2.0-flash-exp."""

    def __init__(self):
        self._model = os.getenv("GEMINI_MODEL", "gemini-2.0-flash-exp")
        self._llm = None

    def _api_key(self) -> str:
        """Baca env saat dipanggil, bukan saat init."""
        return os.getenv("GOOGLE_API_KEY", "")

    def _get_llm(self):
        if self._llm is None:
            from langchain_google_genai import ChatGoogleGenerativeAI
            self._llm = ChatGoogleGenerativeAI(
                google_api_key=self._api_key(),
                model=self._model,
            )
        return self._llm

    @property
    def provider_name(self) -> ProviderName:
        return ProviderName.GEMINI

    @property
    def tier(self) -> ProviderTier:
        return ProviderTier.FREE_CLOUD  # free tier

    @property
    def supports_vision(self) -> bool:
        return True

    @property
    def max_context_tokens(self) -> int:
        return 1000000

    @property
    def is_available(self) -> bool:
        return bool(self._api_key())  # baca env fresh setiap kali

    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
    ) -> GenerationResult:
        from langchain_core.messages import HumanMessage, SystemMessage
        messages = []
        if system_prompt:
            messages.append(SystemMessage(content=system_prompt))
        messages.append(HumanMessage(content=prompt))

        response = await self._get_llm().ainvoke(messages)
        content = response.content

        prompt_tokens = estimate_tokens(prompt + (system_prompt or ""))
        completion_tokens = estimate_tokens(content)

        return GenerationResult(
            content=content,
            provider=self.provider_name,
            model=self._model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            cost_usd=0.0,
        )

    async def stream(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
    ) -> AsyncIterator[str]:
        from langchain_core.messages import HumanMessage, SystemMessage
        messages = []
        if system_prompt:
            messages.append(SystemMessage(content=system_prompt))
        messages.append(HumanMessage(content=prompt))
        async for chunk in self._get_llm().astream(messages):
            yield chunk.content