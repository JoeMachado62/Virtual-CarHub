from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_service_token
from app.core.constants import DealState, ReturnState
from app.core.responses import ok
from app.db.session import get_db
from app.models.entities import Deal, ReturnCase
from app.schemas.returns import ConfirmReceiptRequest, InitiateReturnRequest, RefundRequest
from app.services.audit_service import log_event
from app.services.return_service import confirm_return_receipt, initiate_return, process_refund

router = APIRouter(dependencies=[Depends(require_service_token)])


@router.post("/{deal_id}/initiate")
def initiate(deal_id: str, payload: InitiateReturnRequest, db: Session = Depends(get_db)) -> dict:
    deal = db.get(Deal, deal_id)
    if not deal:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deal not found")

    return_case = initiate_return(
        db,
        deal=deal,
        reason=payload.reason,
        buyer_transport_responsibility=payload.buyer_transport_responsibility,
    )
    db.commit()
    return ok({"return_case_id": return_case.id, "state": return_case.return_state.value})


@router.post("/{deal_id}/confirm-receipt")
def confirm_receipt(deal_id: str, payload: ConfirmReceiptRequest, db: Session = Depends(get_db)) -> dict:
    return_case = db.scalar(select(ReturnCase).where(ReturnCase.deal_id == deal_id))
    if not return_case:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Return case not found")

    confirm_return_receipt(db, return_case=return_case, damage_deduction=payload.damage_deduction)
    return_case.return_state = ReturnState.RETURN_INSPECTING
    return_case.vehicle_received_at = datetime.now(UTC)

    log_event(
        db,
        deal_id=deal_id,
        event_type="return_vehicle_received",
        actor="agent",
        new_state=return_case.return_state.value,
        payload={"damage_deduction": payload.damage_deduction},
    )
    db.commit()
    return ok({"return_case_id": return_case.id, "state": return_case.return_state.value})


@router.post("/{deal_id}/process-refund")
def refund(deal_id: str, payload: RefundRequest, db: Session = Depends(get_db)) -> dict:
    deal = db.get(Deal, deal_id)
    if not deal:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deal not found")

    return_case = db.scalar(select(ReturnCase).where(ReturnCase.deal_id == deal_id))
    if not return_case:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Return case not found")

    updated = process_refund(
        db,
        deal=deal,
        return_case=return_case,
        restocking_fee=payload.restocking_fee,
        damage_deduction=payload.damage_deduction,
    )

    if deal.stage != DealState.CLOSED_LOST:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Refund closeout failed")

    log_event(
        db,
        deal_id=deal.id,
        event_type="return_refund_processed",
        actor="agent",
        payload={
            "refund_amount": updated.refund_amount,
            "restocking_fee": updated.restocking_fee,
            "damage_deduction": updated.damage_deduction,
        },
    )
    db.commit()
    return ok(
        {
            "return_case_id": updated.id,
            "state": updated.return_state.value,
            "refund_amount": updated.refund_amount,
        }
    )
