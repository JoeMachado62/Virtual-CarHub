from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import require_service_token
from app.core.constants import DealState
from app.core.responses import ok
from app.db.session import get_db
from app.models.entities import AcquisitionOrder, Deal
from app.services.audit_service import log_event
from app.services.deal_service import advance_deal_for_trigger

router = APIRouter(dependencies=[Depends(require_service_token)])


@router.post("/{deal_id}/bid")
def submit_bid(deal_id: str, payload: dict, db: Session = Depends(get_db)) -> dict:
    deal = db.get(Deal, deal_id)
    if not deal:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deal not found")

    order = AcquisitionOrder(
        deal_id=deal.id,
        vin=deal.selected_vin,
        acquisition_path="auction",
        bid_ceiling=float(payload.get("bid_ceiling", 0)),
        status="bid_submitted",
    )
    db.add(order)
    log_event(db, deal_id=deal.id, event_type="sourcing_bid_submitted", actor="agent", payload=payload)
    db.commit()
    return ok({"order_id": order.id, "status": order.status})


@router.post("/{deal_id}/dealer-outreach")
def dealer_outreach(deal_id: str, payload: dict, db: Session = Depends(get_db)) -> dict:
    deal = db.get(Deal, deal_id)
    if not deal:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deal not found")

    order = AcquisitionOrder(
        deal_id=deal.id,
        vin=deal.selected_vin,
        acquisition_path="dealer_wholesale",
        actual_price=payload.get("offer_price"),
        status="outreach_sent",
    )
    db.add(order)
    log_event(db, deal_id=deal.id, event_type="sourcing_dealer_outreach", actor="agent", payload=payload)
    db.commit()
    return ok({"order_id": order.id, "status": order.status})


@router.post("/{deal_id}/confirm-acquisition")
def confirm_acquisition(deal_id: str, payload: dict, db: Session = Depends(get_db)) -> dict:
    deal = db.get(Deal, deal_id)
    if not deal:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deal not found")

    if deal.stage != DealState.ACQUISITION_PENDING:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Deal not in acquisition pending")

    advance_deal_for_trigger(
        db,
        deal=deal,
        trigger="acquisition_confirmed",
        payload=payload,
    )
    log_event(db, deal_id=deal.id, event_type="acquisition_confirmed", actor="agent", payload=payload)
    db.commit()
    return ok({"deal_id": deal.id, "stage": deal.stage.value})
