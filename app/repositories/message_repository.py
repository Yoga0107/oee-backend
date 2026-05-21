from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from app.models.ai_models import Message


class MessageRepository:
    def __init__(self, db: Session):
        self._db = db

    def save(
        self,
        conversation_id: str,
        role: str,
        content: str,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        total_tokens: Optional[int] = None,
    ) -> Message:
        msg = Message(
            conversation_id=conversation_id,
            role=role,
            content=content,
            provider=provider,
            model=model,
            total_tokens=total_tokens,
        )
        self._db.add(msg)
        self._db.commit()      # ← commit setiap pesan agar tersimpan permanen
        self._db.refresh(msg)
        return msg

    def get_recent(self, conversation_id: str, limit: int = 10) -> list[dict]:
        """Ambil pesan terbaru sebagai dict untuk memory injection."""
        rows = (
            self._db.query(Message)
            .filter(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.desc())
            .limit(limit)
            .all()
        )
        rows.reverse()  # urutan kronologis
        return [{"role": r.role, "content": r.content} for r in rows]

    def get_all(self, conversation_id: str) -> list[Message]:
        return (
            self._db.query(Message)
            .filter(Message.conversation_id == conversation_id)
            .order_by(Message.created_at)
            .all()
        )
