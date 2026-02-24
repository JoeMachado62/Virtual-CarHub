from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import (
    require_docusign_webhook_auth,
    require_ghl_webhook_auth,
    require_telnyx_webhook_auth,
)
from app.core.responses import ok
from app.db.session import get_db
from app.services.audit_service import log_event

router = APIRouter()


@router.post("/ghl", dependencies=[Depends(require_ghl_webhook_auth)])
def ghl_webhook(payload: dict, db: Session = Depends(get_db)) -> dict:
    log_event(db, deal_id=payload.get("deal_id"), event_type="webhook_ghl", actor="system", payload=payload)
    db.commit()
    return ok({"accepted": True})


@router.post("/docusign", dependencies=[Depends(require_docusign_webhook_auth)])
def docusign_webhook(payload: dict, db: Session = Depends(get_db)) -> dict:
    log_event(
        db,
        deal_id=payload.get("deal_id"),
        event_type="webhook_docusign",
        actor="system",
        payload=payload,
    )
    db.commit()
    return ok({"accepted": True})


@router.post("/telnyx", dependencies=[Depends(require_telnyx_webhook_auth)])
def telnyx_webhook(payload: dict, db: Session = Depends(get_db)) -> dict:
    log_event(
        db,
        deal_id=payload.get("deal_id"),
        event_type="webhook_telnyx",
        actor="system",
        payload=payload,
    )
    db.commit()
    return ok({"accepted": True})
