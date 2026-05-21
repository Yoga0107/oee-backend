import os
from typing import AsyncIterator, Optional

from app.ai.providers.base import (
    BaseLLMProvider,
    GenerationResult,
    ProviderName,
    ProviderTier,
)
from app.ai.token.estimator import estimate_tokens


class GroqProvider(BaseLLMProvider):
    def __init__(self):
        self._model = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
        self._llm = None

    def _api_key(self) -> str:
        return os.getenv("GROQ_API_KEY", "")

    def _get_llm(self):
        if self._llm is None:
            from langchain_groq import ChatGroq
            self._llm = ChatGroq(api_key=self._api_key(), model=self._model)
        return self._llm

    @property
    def provider_name(self) -> ProviderName:
        return ProviderName.GROQ

    @property
    def tier(self) -> ProviderTier:
        return ProviderTier.FREE_CLOUD

    @property
    def supports_vision(self) -> bool:
        return False

    @property
    def max_context_tokens(self) -> int:
        return 131072

    @property
    def is_available(self) -> bool:
        return bool(self._api_key())

    async def generate(self, prompt: str, system_prompt: Optional[str] = None) -> GenerationResult:
        from langchain_core.messages import HumanMessage, SystemMessage
        messages = []
        if system_prompt:
            messages.append(SystemMessage(content=system_prompt))
        messages.append(HumanMessage(content=prompt))
        response = await self._get_llm().ainvoke(messages)
        content = response.content
        pt = estimate_tokens(prompt + (system_prompt or ""))
        ct = estimate_tokens(content)
        return GenerationResult(
            content=content, provider=self.provider_name, model=self._model,
            prompt_tokens=pt, completion_tokens=ct, total_tokens=pt + ct, cost_usd=0.0,
        )

    async def stream(self, prompt: str, system_prompt: Optional[str] = None) -> AsyncIterator[str]:
        from langchain_core.messages import HumanMessage, SystemMessage
        messages = []
        if system_prompt:
            messages.append(SystemMessage(content=system_prompt))
        messages.append(HumanMessage(content=prompt))
        async for chunk in self._get_llm().astream(messages):
            yield chunk.content