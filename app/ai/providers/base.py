from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import AsyncIterator, Optional


class ProviderName(str, Enum):
    OLLAMA = "ollama"
    OPENAI = "openai"
    CLAUDE = "claude"
    GEMINI = "gemini"
    OPENROUTER = "openrouter"
    GROQ = "groq"


class ProviderTier(str, Enum):
    FREE_LOCAL = "free_local"   # Ollama
    FREE_CLOUD = "free_cloud"   # OpenRouter free, Groq free tier
    PAID = "paid"               # OpenAI, Claude, Gemini


@dataclass
class GenerationResult:
    content: str
    provider: ProviderName
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_usd: float = 0.0


class BaseLLMProvider(ABC):
    """Abstract base class for all LLM providers.

    Every provider MUST implement generate() and stream().
    Metadata properties (tier, supports_vision, max_context_tokens)
    drive the intelligent router decisions.
    """

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
    ) -> GenerationResult:
        """Generate a response and return a structured result with token counts."""
        ...

    @abstractmethod
    async def stream(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
    ) -> AsyncIterator[str]:
        """Stream response chunks (for future SSE support)."""
        ...

    @property
    @abstractmethod
    def provider_name(self) -> ProviderName:
        ...

    @property
    @abstractmethod
    def tier(self) -> ProviderTier:
        ...

    @property
    @abstractmethod
    def supports_vision(self) -> bool:
        ...

    @property
    @abstractmethod
    def max_context_tokens(self) -> int:
        ...

    @property
    @abstractmethod
    def is_available(self) -> bool:
        """Return False if required API key / service is missing."""
        ...
