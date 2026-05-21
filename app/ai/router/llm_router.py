"""
Intelligent LLM Router.

Applies rule-based routing to select the best provider for each request.
Routing priority:
  1. Free local  (Ollama)
  2. Free cloud  (Groq, OpenRouter)
  3. Paid cloud  (OpenAI, Claude, Gemini)

Rules are evaluated in order; the first matching rule wins.
If the selected provider is unavailable, fallback chain kicks in.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from enum import Enum, auto
from typing import Optional, Sequence

from app.ai.providers.base import BaseLLMProvider, ProviderName, ProviderTier
from app.ai.token.estimator import estimate_tokens

logger = logging.getLogger(__name__)

# ── Thresholds ────────────────────────────────────────────────────────────────
_HIGH_TOKEN_THRESHOLD = 3000     # tokens in a single message
_LONG_DOC_THRESHOLD = 1500

# ── Keyword sets ──────────────────────────────────────────────────────────────
_GREETING_PATTERNS = re.compile(
    r"\b(halo|helo|hi|hey|hello|selamat\s+(pagi|siang|sore|malam)|apa\s+kabar|hai)\b",
    re.IGNORECASE,
)
_FAQ_PATTERNS = re.compile(
    r"\b(apa\s+itu|what\s+is|define|definisi|pengertian|jelaskan\s+singkat|artinya)\b",
    re.IGNORECASE,
)
_CONFIDENTIAL_PATTERNS = re.compile(
    r"\b(rahasia|confidential|internal|data\s+perusahaan|company\s+data|private|SAP|ERP)\b",
    re.IGNORECASE,
)
_REASONING_PATTERNS = re.compile(
    r"\b(analisis|analyze|bandingkan|compare|evaluasi|evaluate|mengapa|why|bagaimana\s+cara|"
    r"strategi|strategy|rekomendasi|recommend|root\s*cause|RCA|troubleshoot)\b",
    re.IGNORECASE,
)
_SUMMARIZE_PATTERNS = re.compile(
    r"\b(ringkas|summarize|summary|rangkuman|rekap|recap|kesimpulan|conclusion)\b",
    re.IGNORECASE,
)
_IMAGE_PATTERNS = re.compile(
    r"\b(gambar|image|foto|photo|visual|screenshot|chart|diagram|multimodal)\b",
    re.IGNORECASE,
)


class RoutingReason(str, Enum):
    GREETING = "greeting"
    SIMPLE_FAQ = "simple_faq"
    CONFIDENTIAL = "confidential_data"
    HIGH_TOKEN = "high_token_count"
    LONG_DOCUMENT = "long_document"
    IMAGE_REQUEST = "image_multimodal"
    COMPLEX_REASONING = "complex_reasoning"
    DEFAULT = "default"


@dataclass
class RoutingDecision:
    provider_name: ProviderName
    reason: RoutingReason
    estimated_tokens: int
    fallback_chain: list[ProviderName]


class LLMRouter:
    """Routes a user message to the most cost-efficient capable provider.

    Provider registry is injected so the router has no hard dependency
    on any concrete provider class — stays testable and extensible.
    """

    def __init__(self, providers: dict[ProviderName, BaseLLMProvider]):
        self._providers = providers

    def get_provider(self, name: ProviderName) -> BaseLLMProvider:
        provider = self._providers.get(name)
        if provider is None:
            raise ValueError(f"Provider '{name}' not registered.")
        return provider

    def available_providers(self) -> list[BaseLLMProvider]:
        return [p for p in self._providers.values() if p.is_available]

    def _first_available(self, *candidates: ProviderName) -> Optional[ProviderName]:
        for name in candidates:
            p = self._providers.get(name)
            if p and p.is_available:
                return name
        return None

    def _build_fallback_chain(self, primary: ProviderName) -> list[ProviderName]:
        """Build ordered fallback list excluding the primary."""
        # Prefer free tiers first, then paid
        order = [
            ProviderName.OLLAMA,
            ProviderName.GROQ,
            ProviderName.OPENROUTER,
            ProviderName.OPENAI,
            ProviderName.GEMINI,
            ProviderName.CLAUDE,
        ]
        return [p for p in order if p != primary and self._providers.get(p) and self._providers[p].is_available]

    def route(self, message: str, has_image: bool = False) -> RoutingDecision:
        """Analyse the message and return a RoutingDecision.

        Routing priority (first match wins):
        1.  Confidential keywords  → Ollama (never leaves local)
        2.  Image request          → Gemini (vision)
        3.  Long document          → Claude (200K context)
        4.  High token count       → Groq / OpenRouter (free, large context)
        5.  Complex reasoning      → OpenAI GPT
        6.  Simple FAQ             → Ollama
        7.  Greeting / casual      → Groq (fast, free)
        8.  Default                → Ollama
        """
        token_count = estimate_tokens(message)

        # ── Rule 1: Confidential / internal data → MUST stay local ──────────
        if _CONFIDENTIAL_PATTERNS.search(message):
            chosen = ProviderName.OLLAMA
            reason = RoutingReason.CONFIDENTIAL

        # ── Rule 2: Image / multimodal ───────────────────────────────────────
        elif has_image or _IMAGE_PATTERNS.search(message):
            chosen = self._first_available(ProviderName.GEMINI, ProviderName.CLAUDE) or ProviderName.OLLAMA
            reason = RoutingReason.IMAGE_REQUEST

        # ── Rule 3: Long document / summarization ────────────────────────────
        elif _SUMMARIZE_PATTERNS.search(message) or token_count > _LONG_DOC_THRESHOLD:
            chosen = self._first_available(ProviderName.CLAUDE, ProviderName.OPENAI, ProviderName.GEMINI) or ProviderName.OLLAMA
            reason = RoutingReason.LONG_DOCUMENT

        # ── Rule 4: High token count → free large-context providers ──────────
        elif token_count > _HIGH_TOKEN_THRESHOLD:
            chosen = self._first_available(ProviderName.GROQ, ProviderName.OPENROUTER, ProviderName.OLLAMA) or ProviderName.OLLAMA
            reason = RoutingReason.HIGH_TOKEN

        # ── Rule 5: Complex reasoning ────────────────────────────────────────
        elif _REASONING_PATTERNS.search(message):
            chosen = self._first_available(ProviderName.OPENAI, ProviderName.CLAUDE, ProviderName.GROQ) or ProviderName.OLLAMA
            reason = RoutingReason.COMPLEX_REASONING

        # ── Rule 6: Simple FAQ ───────────────────────────────────────────────
        elif _FAQ_PATTERNS.search(message):
            chosen = self._first_available(ProviderName.OLLAMA, ProviderName.GROQ) or ProviderName.OLLAMA
            reason = RoutingReason.SIMPLE_FAQ

        # ── Rule 7: Greeting / casual ────────────────────────────────────────
        elif _GREETING_PATTERNS.search(message):
            chosen = self._first_available(ProviderName.GROQ, ProviderName.OPENROUTER, ProviderName.OLLAMA) or ProviderName.OLLAMA
            reason = RoutingReason.GREETING

        # ── Rule 8: Default ──────────────────────────────────────────────────
        else:
            chosen = self._first_available(ProviderName.OLLAMA, ProviderName.GROQ) or ProviderName.OLLAMA
            reason = RoutingReason.DEFAULT

        logger.info("LLMRouter.route | reason=%s | provider=%s | tokens≈%d", reason, chosen, token_count)

        return RoutingDecision(
            provider_name=chosen,
            reason=reason,
            estimated_tokens=token_count,
            fallback_chain=self._build_fallback_chain(chosen),
        )
