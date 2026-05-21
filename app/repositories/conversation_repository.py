from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from app.models.ai_models import Conversation


class ConversationRepository:
    def __init__(self, db: Session):
        self._db = db

    def create(self, conversation_id: str, user_id: Optional[str], title: str) -> Conversation:
        conv = Conversation(id=conversation_id, user_id=user_id, title=title)
        self._db.add(conv)
        self._db.commit()      # ← langsung commit agar FK valid untuk insert berikutnya
        self._db.refresh(conv)
        return conv

    def get(self, conversation_id: str) -> Optional[Conversation]:
        return self._db.query(Conversation).filter(Conversation.id == conversation_id).first()

    def list_by_user(self, user_id: str, limit: int = 30) -> list[Conversation]:
        from sqlalchemy import desc
        return (
            self._db.query(Conversation)
            .filter(Conversation.user_id == user_id)
            .order_by(desc(Conversation.updated_at))
            .limit(limit)
            .all()
        )

    def delete(self, conversation_id: str) -> None:
        conv = self.get(conversation_id)
        if conv:
            self._db.delete(conv)
            self._db.commit()
