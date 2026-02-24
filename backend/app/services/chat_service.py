from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.entities import ChatMessage, Deal, VehicleMatch


def respond_to_message(db: Session, *, user_id: str, message: str) -> tuple[str, bool]:
    normalized = message.lower().strip()
    deal = db.scalar(
        select(Deal).where(Deal.user_id == user_id).order_by(Deal.created_at.desc()).limit(1)
    )

    escalation = False
    if any(term in normalized for term in ["lawyer", "attorney", "complaint", "human"]):
        escalation = True
        reply = (
            "I flagged this for a human team member and scheduled a callback. "
            "A specialist will reach out within 2 business hours."
        )
    elif "status" in normalized and deal:
        reply = (
            f"Your current deal stage is {deal.stage.value}. "
            "I can also walk you through the next required tasks if you want."
        )
    elif "recommend" in normalized:
        count = db.scalar(
            select(func.count(VehicleMatch.id)).where(VehicleMatch.user_id == user_id)
        )
        reply = f"You currently have {count or 0} active recommendations."
    elif "return" in normalized:
        reply = "If your delivery was within 7 calendar days, I can start your return now."
    else:
        reply = (
            "I can help with deal status, recommendations, documents, delivery tracking, "
            "or initiating a return."
        )

    db.add(ChatMessage(user_id=user_id, deal_id=deal.id if deal else None, role="user", message=message))
    db.add(ChatMessage(user_id=user_id, deal_id=deal.id if deal else None, role="assistant", message=reply))
    db.flush()
    return reply, escalation
