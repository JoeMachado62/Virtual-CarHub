from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.entities import Notification


def create_notification(
    db: Session,
    *,
    user_id: str,
    message: str,
    deal_id: str | None = None,
    channel: str = "in_app",
) -> Notification:
    notification = Notification(
        user_id=user_id,
        deal_id=deal_id,
        message=message,
        channel=channel,
    )
    db.add(notification)
    db.flush()
    return notification
