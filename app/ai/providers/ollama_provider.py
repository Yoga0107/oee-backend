import os
from typing import AsyncIterator, Optional

from langchain_ollama import OllamaLLM

from app.ai.providers.base import (
    BaseLLMProvider,
    GenerationResult,
    ProviderName,
    ProviderTier,
)
from app.ai.token.estimator import estimate_tokens


class OllamaProvider(BaseLLMProvider):
    """Local Ollama provider — always free, always private."""

    def __init__(self):
        self._base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        self._model = os.getenv("DEFAULT_MODEL", "qwen2.5:3b")
        self._llm = OllamaLLM(base_url=self._base_url, model=self._model)

    @property
    def provider_name(self) -> ProviderName:
        return ProviderName.OLLAMA

    @property
    def tier(self) -> ProviderTier:
        return ProviderTier.FREE_LOCAL

    @property
    def supports_vision(self) -> bool:
        return False

    @property
    def max_context_tokens(self) -> int:
        return 8192

    @property
    def is_available(self) -> bool:
        return True  # Always available as local fallback

    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
    ) -> GenerationResult:
        full_prompt = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt
        response: str = await self._llm.ainvoke(full_prompt)

        prompt_tokens = estimate_tokens(full_prompt)
        completion_tokens = estimate_tokens(response)

        return GenerationResult(
            content=response,
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
        full_prompt = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt
        async for chunk in self._llm.astream(full_prompt):
            yield chunk
