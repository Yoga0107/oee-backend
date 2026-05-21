from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.ai_models import ProviderLog


class ProviderLogRepository:
    def __init__(self, db: Session):
        self._db = db

    def log(
        self,
        conversation_id: str,
        provider: str,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        total_tokens: int,
        cost_usd: float,
        routing_reason: str,
    ) -> ProviderLog:
        entry = ProviderLog(
            conversation_id=conversation_id,
            provider=provider,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            cost_usd=cost_usd,
            routing_reason=routing_reason,
        )
        self._db.add(entry)
        self._db.commit()      # ← commit log
        self._db.refresh(entry)
        return entry
