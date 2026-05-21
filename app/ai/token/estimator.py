"""
Token estimation utilities.

For production accuracy, use tiktoken for OpenAI models.
For all others we use a fast approximation: 1 token ≈ 4 characters.
This avoids adding a heavy dependency for every provider.
"""
import math


def estimate_tokens(text: str) -> int:
    """Estimate token count from text length.

    Rule of thumb: 1 token ≈ 4 characters for English text.
    Indonesian / mixed text skews slightly higher (~3.5 chars/token).
    We use 3.5 to be conservative (overestimate = safer budget planning).
    """
    if not text:
        return 0
    return math.ceil(len(text) / 3.5)


def token_budget_exceeded(text: str, max_tokens: int) -> bool:
    return estimate_tokens(text) > max_tokens


def truncate_to_token_budget(text: str, max_tokens: int) -> str:
    """Truncate text so it fits within an approximate token budget."""
    max_chars = int(max_tokens * 3.5)
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n...[truncated for token budget]"
