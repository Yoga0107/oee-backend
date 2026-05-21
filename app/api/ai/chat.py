"""
Phase 2 AI chat API endpoints.
User-aware: setiap conversation terikat ke authenticated user.
Kompatibel dengan CurrentUser = Annotated[User, Depends(get_current_user)]
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.ai.orchestrator.ai_orchestrator import AIOrchestrator
from app.ai.providers.base import ProviderName
from app.ai.services.dependencies import get_orchestrator
from app.core.deps import CurrentUser          # ← Annotated type, tidak perlu Depends lagi
from app.db.database import get_db
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.message_repository import MessageRepository

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/ai", tags=["AI Chat"])


# ── Schemas ────────────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=8000)
    conversation_id: Optional[str] = Field(
        None, description="Kosongkan untuk mulai percakapan baru."
    )
    provider: Optional[ProviderName] = Field(
        None, description="Paksa provider tertentu (opsional, override auto-routing)."
    )


class ChatResponse(BaseModel):
    response: str
    conversation_id: str
    provider: str
    model: str
    routing_reason: str
    total_tokens: int
    cost_usd: float


class ConversationSummary(BaseModel):
    id: str
    title: str
    created_at: str
    updated_at: str


class MessageOut(BaseModel):
    id: int
    role: str
    content: str
    provider: Optional[str]
    model: Optional[str]
    created_at: str


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.post("/chat", response_model=ChatResponse, status_code=status.HTTP_200_OK)
async def chat(
    request: ChatRequest,
    current_user: CurrentUser,                 # ← cukup ini, tanpa = Depends(...)
    orchestrator: AIOrchestrator = Depends(get_orchestrator),
):
    """Kirim pesan. Conversation otomatis terikat ke user yang login."""
    try:
        result = await orchestrator.chat(
            user_message=request.message,
            conversation_id=request.conversation_id,
            user_id=str(current_user.id),
            force_provider=request.provider,
        )
        return ChatResponse(
            response=result.content,
            conversation_id=result.conversation_id,
            provider=result.provider.value,
            model=result.model,
            routing_reason=result.routing_reason,
            total_tokens=result.total_tokens,
            cost_usd=result.cost_usd,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Unexpected error in /api/ai/chat: %s", exc)
        raise HTTPException(status_code=500, detail="Internal server error.") from exc


@router.get("/conversations", response_model=list[ConversationSummary])
def list_conversations(
    current_user: CurrentUser,                 # ← cukup ini, tanpa = Depends(...)
    limit: int = 30,
    db: Session = Depends(get_db),
):
    """Daftar semua percakapan milik user yang sedang login."""
    repo = ConversationRepository(db)
    convs = repo.list_by_user(user_id=str(current_user.id), limit=limit)
    return [
        ConversationSummary(
            id=c.id,
            title=c.title,
            created_at=c.created_at.isoformat(),
            updated_at=c.updated_at.isoformat(),
        )
        for c in convs
    ]


@router.get(
    "/conversations/{conversation_id}/messages",
    response_model=list[MessageOut],
)
def get_messages(
    conversation_id: str,
    current_user: CurrentUser,                 # ← cukup ini, tanpa = Depends(...)
    db: Session = Depends(get_db),
):
    """Ambil semua pesan dalam satu percakapan. Hanya milik sendiri."""
    conv_repo = ConversationRepository(db)
    conv = conv_repo.get(conversation_id)

    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    if conv.user_id != str(current_user.id):
        raise HTTPException(status_code=403, detail="Access denied: bukan conversation Anda.")

    repo = MessageRepository(db)
    messages = repo.get_all(conversation_id)
    return [
        MessageOut(
            id=m.id,
            role=m.role,
            content=m.content,
            provider=m.provider,
            model=m.model,
            created_at=m.created_at.isoformat(),
        )
        for m in messages
    ]


@router.delete(
    "/conversations/{conversation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_conversation(
    conversation_id: str,
    current_user: CurrentUser,                 # ← cukup ini, tanpa = Depends(...)
    db: Session = Depends(get_db),
):
    """Hapus conversation. Hanya bisa hapus milik sendiri."""
    repo = ConversationRepository(db)
    conv = repo.get(conversation_id)

    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    if conv.user_id != str(current_user.id):
        raise HTTPException(status_code=403, detail="Access denied: bukan conversation Anda.")

    repo.delete(conversation_id)
    
@router.get("/providers/status")
def provider_status(
    current_user: CurrentUser,
    orchestrator: AIOrchestrator = Depends(get_orchestrator),
):
    """Cek status semua provider — apakah API key tersedia."""
    result = {}
    for name, provider in orchestrator._router._providers.items():
        result[name.value] = {
            "available": provider.is_available,
            "tier": provider.tier.value,
            "model": getattr(provider, "_model", "unknown"),
        }
    return result
