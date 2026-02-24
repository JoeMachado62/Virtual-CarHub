from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.responses import ok
from app.db.session import get_db
from app.models.entities import ChatMessage, User
from app.schemas.chat import ChatMessageRequest
from app.services.chat_service import respond_to_message

router = APIRouter()


@router.post("/message")
def post_message(
    payload: ChatMessageRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    reply, escalation = respond_to_message(db, user_id=current_user.id, message=payload.message)
    db.commit()
    return ok({"reply": reply, "escalation_triggered": escalation})


@router.get("/history")
def get_history(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    rows = db.scalars(
        select(ChatMessage)
        .where(ChatMessage.user_id == current_user.id)
        .order_by(ChatMessage.created_at.desc())
        .limit(100)
    ).all()
    return ok(
        [
            {
                "id": row.id,
                "role": row.role,
                "message": row.message,
                "created_at": row.created_at,
            }
            for row in reversed(rows)
        ]
    )
