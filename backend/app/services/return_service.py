from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.constants import DealState, ReturnState
from app.models.entities import Deal, ReturnCase
from app.services.audit_service import log_event
from app.services.deal_service import transition_deal_state
from app.services.external_sync_service import get_external_sync_service


RETURN_WINDOW_DAYS = 7


def initiate_return(
    db: Session,
    *,
    deal: Deal,
    reason: str,
    buyer_transport_responsibility: bool,
) -> ReturnCase:
    if deal.stage != DealState.DELIVERED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Return can only be initiated from DELIVERED state",
        )

    if not deal.delivered_at:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Delivery timestamp missing",
        )

    now = datetime.now(UTC)
    delivered_at = deal.delivered_at
    if delivered_at.tzinfo is None:
        delivered_at = delivered_at.replace(tzinfo=UTC)

    if now > delivered_at + timedelta(days=RETURN_WINDOW_DAYS):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Return window has expired",
        )

    existing = db.scalar(select(ReturnCase).where(ReturnCase.deal_id == deal.id))
    if existing:
        return existing

    return_case = ReturnCase(
        deal_id=deal.id,
        vin=deal.selected_vin or "UNKNOWN",
        return_reason=reason,
        return_state=ReturnState.RETURN_PENDING,
        buyer_transport_responsibility=buyer_transport_responsibility,
        initiated_at=now,
    )
    db.add(return_case)

    transition_deal_state(
        db,
        deal=deal,
        new_state=DealState.RETURN_PENDING,
        actor="buyer",
        reason="buyer_initiated_return",
        payload={"return_reason": reason},
    )

    log_event(
        db,
        deal_id=deal.id,
        event_type="return_initiated",
        actor="buyer",
        new_state=ReturnState.RETURN_PENDING.value,
        payload={"reason": reason},
    )

    user = deal.user
    if user:
        try:
            envelope = get_external_sync_service().send_return_authorization(user=user, deal=deal)
            if envelope:
                log_event(
                    db,
                    deal_id=deal.id,
                    event_type="return_authorization_sent",
                    actor="system",
                    payload={"envelope_id": envelope.get("envelopeId")},
                )
        except Exception:
            pass

    db.flush()
    return return_case


def confirm_return_receipt(db: Session, *, return_case: ReturnCase, damage_deduction: float = 0.0) -> ReturnCase:
    return_case.return_state = ReturnState.RETURN_INSPECTING
    return_case.vehicle_received_at = datetime.now(UTC)
    return_case.damage_deduction = max(0.0, damage_deduction)
    db.flush()
    return return_case


def process_refund(
    db: Session,
    *,
    deal: Deal,
    return_case: ReturnCase,
    restocking_fee: float,
    damage_deduction: float,
) -> ReturnCase:
    restocking_fee = max(0.0, restocking_fee)
    damage_deduction = max(0.0, damage_deduction)

    buyer_payment = 5000.0
    refund = max(0.0, buyer_payment - restocking_fee - damage_deduction)

    return_case.restocking_fee = restocking_fee
    return_case.damage_deduction = damage_deduction
    return_case.refund_amount = refund
    return_case.return_state = ReturnState.RETURN_APPROVED

    transition_deal_state(
        db,
        deal=deal,
        new_state=DealState.CLOSED_LOST,
        actor="system",
        reason="return_refund_processed",
        payload={"refund_amount": refund},
    )
    db.flush()
    return return_case
