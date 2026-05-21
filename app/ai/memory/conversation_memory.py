"""
Conversation memory dengan sliding window.
Sync version — kompatibel dengan SessionLocal dari app/db/database.py
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List

from app.ai.token.estimator import estimate_tokens

_WINDOW_SIZE = 10           # max pesan yang diambil
_MAX_CONTEXT_TOKENS = 2000  # hard cap token history yang diinject


@dataclass
class MemoryMessage:
    role: str    # "user" | "assistant"
    content: str


class ConversationMemory:
    """Ambil dan format sliding window dari riwayat percakapan."""

    def __init__(self, message_repo):
        self._message_repo = message_repo

    def get_context(self, conversation_id: str) -> List[MemoryMessage]:
        """Ambil _WINDOW_SIZE pesan terakhir dari database (sync)."""
        rows = self._message_repo.get_recent(
            conversation_id=conversation_id,
            limit=_WINDOW_SIZE,
        )
        return [MemoryMessage(role=r["role"], content=r["content"]) for r in rows]

    def format_prompt(self, history: List[MemoryMessage], new_message: str) -> str:
        """Gabungkan history + pesan baru menjadi satu string prompt."""
        if not history:
            return new_message

        # Drop pesan lama jika melebihi token budget
        while history:
            dialogue_lines = [
                f"{'User' if m.role == 'user' else 'Assistant'}: {m.content}"
                for m in history
            ]
            dialogue = "\n".join(dialogue_lines)
            if estimate_tokens(dialogue) <= _MAX_CONTEXT_TOKENS:
                break
            history = history[1:]

        return (
            "Previous conversation:\n"
            f"{dialogue}\n\n"
            "---\n"
            f"User: {new_message}"
        )
