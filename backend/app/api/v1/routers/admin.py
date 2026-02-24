from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_service_token
from app.core.constants import DealState
from app.core.responses import ok
from app.db.session import get_db
from app.models.entities import AuditEvent, Deal, ReturnCase
from app.schemas.deal import OverrideStateRequest
from app.services.deal_service import transition_deal_state

router = APIRouter(dependencies=[Depends(require_service_token)])


@router.get("/deals")
def get_deals(db: Session = Depends(get_db)) -> dict:
    deals = db.scalars(select(Deal).order_by(Deal.created_at.desc()).limit(500)).all()
    return ok(
        [
            {
                "id": deal.id,
                "user_id": deal.user_id,
                "stage": deal.stage.value,
                "funding_state": deal.funding_state.value,
                "human_checkpoint_required": deal.human_checkpoint_required,
                "selected_vin": deal.selected_vin,
                "ghl_opportunity_id": deal.ghl_opportunity_id,
                "created_at": deal.created_at,
            }
            for deal in deals
        ]
    )


@router.get("/deals/{deal_id}")
def get_deal(deal_id: str, db: Session = Depends(get_db)) -> dict:
    deal = db.get(Deal, deal_id)
    if not deal:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deal not found")
    return ok(
        {
            "id": deal.id,
            "stage": deal.stage.value,
            "funding_state": deal.funding_state.value,
            "assigned_agent": deal.assigned_agent,
            "human_checkpoint_required": deal.human_checkpoint_required,
            "selected_vin": deal.selected_vin,
            "ghl_contact_id": deal.ghl_contact_id,
            "ghl_opportunity_id": deal.ghl_opportunity_id,
            "created_at": deal.created_at,
            "updated_at": deal.updated_at,
        }
    )


@router.post("/deals/{deal_id}/override-state")
def override_state(deal_id: str, payload: OverrideStateRequest, db: Session = Depends(get_db)) -> dict:
    deal = db.get(Deal, deal_id)
    if not deal:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deal not found")

    transition_deal_state(
        db,
        deal=deal,
        new_state=payload.new_state,
        actor="human",
        reason=payload.reason,
        payload={"override": True},
    )
    db.commit()
    return ok({"deal_id": deal.id, "new_state": payload.new_state.value})


@router.get("/exceptions")
def get_exceptions(db: Session = Depends(get_db)) -> dict:
    rows = db.scalars(
        select(AuditEvent)
        .where(
            AuditEvent.new_state == DealState.EXCEPTION.value,
        )
        .order_by(AuditEvent.timestamp.desc())
        .limit(200)
    ).all()
    return ok(
        [
            {
                "deal_id": row.deal_id,
                "event_type": row.event_type,
                "actor": row.actor,
                "timestamp": row.timestamp,
                "payload": row.payload_json,
            }
            for row in rows
        ]
    )


@router.get("/audit-log")
def get_audit_log(db: Session = Depends(get_db)) -> dict:
    rows = db.scalars(select(AuditEvent).order_by(AuditEvent.timestamp.desc()).limit(500)).all()
    return ok(
        [
            {
                "id": row.id,
                "deal_id": row.deal_id,
                "event_type": row.event_type,
                "actor": row.actor,
                "previous_state": row.previous_state,
                "new_state": row.new_state,
                "payload": row.payload_json,
                "timestamp": row.timestamp,
            }
            for row in rows
        ]
    )


@router.get("/agents/activity")
def get_agent_activity(db: Session = Depends(get_db)) -> dict:
    rows = db.scalars(
        select(AuditEvent)
        .where(AuditEvent.actor.in_(["agent", "system"]))
        .order_by(AuditEvent.timestamp.desc())
        .limit(500)
    ).all()
    return ok(
        [
            {
                "deal_id": row.deal_id,
                "event_type": row.event_type,
                "actor": row.actor,
                "timestamp": row.timestamp,
            }
            for row in rows
        ]
    )


@router.get("/returns")
def get_returns(db: Session = Depends(get_db)) -> dict:
    rows = db.scalars(select(ReturnCase).order_by(ReturnCase.created_at.desc()).limit(200)).all()
    return ok(
        [
            {
                "id": row.id,
                "deal_id": row.deal_id,
                "vin": row.vin,
                "return_reason": row.return_reason,
                "return_state": row.return_state.value,
                "refund_amount": row.refund_amount,
                "initiated_at": row.initiated_at,
            }
            for row in rows
        ]
    )
