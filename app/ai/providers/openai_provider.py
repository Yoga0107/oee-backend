import os
from typing import AsyncIterator, Optional

from app.ai.providers.base import (
    BaseLLMProvider,
    GenerationResult,
    ProviderName,
    ProviderTier,
)
from app.ai.token.estimator import estimate_tokens

# GPT-4o-mini pricing per 1K tokens (USD)
_INPUT_COST_PER_1K = 0.000150
_OUTPUT_COST_PER_1K = 0.000600


class OpenAIProvider(BaseLLMProvider):
    """OpenAI provider — GPT-4o-mini by default for cost efficiency."""

    def __init__(self):
        self._api_key = os.getenv("OPENAI_API_KEY", "")
        self._model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        self._llm = None

    def _get_llm(self):
        if self._llm is None:
            from langchain_openai import ChatOpenAI
            self._llm = ChatOpenAI(api_key=self._api_key, model=self._model)
        return self._llm

    @property
    def provider_name(self) -> ProviderName:
        return ProviderName.OPENAI

    @property
    def tier(self) -> ProviderTier:
        return ProviderTier.PAID

    @property
    def supports_vision(self) -> bool:
        return False

    @property
    def max_context_tokens(self) -> int:
        return 128000

    @property
    def is_available(self) -> bool:
        return bool(self._api_key)

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
        cost = (prompt_tokens / 1000 * _INPUT_COST_PER_1K) + (completion_tokens / 1000 * _OUTPUT_COST_PER_1K)

        return GenerationResult(
            content=content,
            provider=self.provider_name,
            model=self._model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            cost_usd=cost,
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
