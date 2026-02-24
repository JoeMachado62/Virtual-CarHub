from sqlalchemy.orm import Session

from app.models.entities import AuditEvent


def log_event(
    db: Session,
    *,
    deal_id: str | None,
    event_type: str,
    actor: str,
    previous_state: str | None = None,
    new_state: str | None = None,
    payload: dict | None = None,
) -> AuditEvent:
    event = AuditEvent(
        deal_id=deal_id,
        event_type=event_type,
        actor=actor,
        previous_state=previous_state,
        new_state=new_state,
        payload_json=payload or {},
    )
    db.add(event)
    db.flush()
    return event
