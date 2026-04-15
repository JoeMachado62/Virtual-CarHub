from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_service_token
from app.core.constants import DealState
from app.core.responses import ok
from app.db.session import get_db
from app.models.entities import Deal, Shipment
from app.services.audit_service import log_event
from app.services.deal_service import advance_deal_for_trigger

router = APIRouter(dependencies=[Depends(require_service_token)])


@router.post("/{deal_id}/request-quotes")
def request_quotes(deal_id: str, payload: dict, db: Session = Depends(get_db)) -> dict:
    deal = db.get(Deal, deal_id)
    if not deal:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deal not found")

    quotes = [
        {"carrier": "Fast Lane Transport", "cost": 925, "eta_days": 4},
        {"carrier": "RoadRunner Auto", "cost": 990, "eta_days": 3},
        {"carrier": "Budget Haul", "cost": 870, "eta_days": 6},
    ]
    log_event(db, deal_id=deal.id, event_type="logistics_quotes_requested", actor="agent", payload=payload)
    db.commit()
    return ok({"quotes": quotes})


@router.post("/{deal_id}/book-carrier")
def book_carrier(deal_id: str, payload: dict, db: Session = Depends(get_db)) -> dict:
    deal = db.get(Deal, deal_id)
    if not deal:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deal not found")

    shipment = db.scalar(select(Shipment).where(Shipment.deal_id == deal.id))
    if not shipment:
        shipment = Shipment(deal_id=deal.id, vin=deal.selected_vin or "UNKNOWN")
        db.add(shipment)

    shipment.status = "in_transit"
    shipment.tracking_url = payload.get("tracking_url", "https://tracking.virtualcarhub.local/placeholder")
    shipment.eta = datetime.now(UTC) + timedelta(days=int(payload.get("eta_days", 5)))

    advance_deal_for_trigger(db, deal=deal, trigger="carrier_booked")

    log_event(db, deal_id=deal.id, event_type="logistics_carrier_booked", actor="agent", payload=payload)
    db.commit()
    return ok({"shipment_id": shipment.id, "status": shipment.status, "eta": shipment.eta})


@router.get("/{deal_id}/tracking")
def get_tracking(deal_id: str, db: Session = Depends(get_db)) -> dict:
    shipment = db.scalar(select(Shipment).where(Shipment.deal_id == deal_id))
    if not shipment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shipment not found")

    return ok(
        {
            "status": shipment.status,
            "tracking_url": shipment.tracking_url,
            "eta": shipment.eta,
            "delivered_at": shipment.delivered_at,
        }
    )
