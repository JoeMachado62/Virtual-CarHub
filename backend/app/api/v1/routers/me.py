from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_deal, get_current_user
from app.core.constants import DealState
from app.core.responses import ok
from app.db.session import get_db
from app.models.entities import Document, GarageItem, Notification, Shipment, User, Vehicle, VehicleMatch
from app.schemas.profile import ProfileUpdateRequest, QuickMatchRequest
from app.schemas.returns import InitiateReturnRequest
from app.services.deal_service import advance_deal_to, transition_deal_state
from app.services.image_pipeline_service import (
    ensure_tier3_processing_job,
    resolve_vehicle_card_media,
    resolve_vehicle_display_context,
)
from app.services.matching_service import run_matching
from app.services.profile_service import apply_full_profile, apply_quick_match, get_or_create_profile
from app.services.return_service import initiate_return

router = APIRouter()


def _normalize_vin(vin: str) -> str:
    normalized = vin.strip().upper()
    if len(normalized) != 17:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="VIN must be 17 characters")
    return normalized


def _serialize_garage_item(
    db: Session,
    item: GarageItem,
    vehicle: Vehicle | None,
    *,
    deal_stage: DealState,
) -> dict:
    if vehicle:
        media = resolve_vehicle_card_media(db, vehicle=vehicle, deal_stage=deal_stage, deal_id=item.deal_id)
        display_context = resolve_vehicle_display_context(
            db,
            vehicle=vehicle,
            deal_stage=deal_stage,
            deal_id=item.deal_id,
        )
        thumbnail = media.thumbnail
        display_mode = media.display_mode.value
        inspection_status = media.inspection_status.value
        has_inspection_report = media.has_inspection_report
    else:
        thumbnail = None
        display_mode = "MARKETING"
        inspection_status = "NOT_STARTED"
        has_inspection_report = False
        display_context = {}

    return {
        "id": item.id,
        "vin": item.vin,
        "status": item.status,
        "source": item.source,
        "added_at": item.created_at,
        "updated_at": item.updated_at,
        "acquisition_started_at": item.acquisition_started_at,
        "deal_stage": deal_stage.value,
        "display_mode": display_mode,
        "inspection_status": inspection_status,
        "has_inspection_report": has_inspection_report,
        "display_context": display_context,
        "vehicle": {
            "year": vehicle.year if vehicle else None,
            "make": vehicle.make if vehicle else None,
            "model": vehicle.model if vehicle else None,
            "trim": vehicle.trim if vehicle else None,
            "price_asking": vehicle.price_asking if vehicle else None,
            "odometer": vehicle.odometer if vehicle else None,
            "location_state": vehicle.location_state if vehicle else None,
            "location_zip": vehicle.location_zip if vehicle else None,
            "source_type": vehicle.source_type if vehicle else None,
            "thumbnail": thumbnail,
        },
    }


def _ensure_vehicle_match(
    db: Session,
    *,
    deal_id: str,
    user_id: str,
    vehicle: Vehicle,
    status_value: str,
    explainability: str,
) -> VehicleMatch:
    match = db.scalar(
        select(VehicleMatch).where(VehicleMatch.deal_id == deal_id, VehicleMatch.vin == vehicle.vin)
    )
    base_price = float(vehicle.price_asking or 0)
    estimated_otd = round(base_price * 1.1, 2) if base_price else 0.0
    market_retail = float(vehicle.price_wholesale_est or vehicle.price_asking or 0)
    savings = max(round(market_retail - estimated_otd, 2), 0.0) if market_retail else 0.0

    if not match:
        match = VehicleMatch(
            deal_id=deal_id,
            user_id=user_id,
            vin=vehicle.vin,
            status=status_value,
            match_score=0.5,
            explainability_text=explainability,
            marketcheck_retail=market_retail or None,
            estimated_otd=estimated_otd,
            danny_savings=savings,
        )
        db.add(match)
        return match

    match.status = status_value
    if not match.explainability_text:
        match.explainability_text = explainability
    if match.marketcheck_retail is None and market_retail:
        match.marketcheck_retail = market_retail
    if not match.estimated_otd and estimated_otd:
        match.estimated_otd = estimated_otd
    return match


@router.get("/profile")
def get_profile(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    profile = get_or_create_profile(db, current_user.id)
    db.commit()
    return ok(
        {
            "profile_tier": profile.profile_tier.value,
            "version": profile.version,
            "bfv_json": profile.bfv_json,
            "intake_steps_complete": profile.intake_steps_complete,
            "hard_constraints": profile.hard_constraints,
            "demographics": profile.demographics,
            "is_complete": profile.is_complete,
        }
    )


@router.put("/profile")
def put_profile(
    payload: ProfileUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    current_deal=Depends(get_current_deal),
) -> dict:
    profile = get_or_create_profile(db, current_user.id)
    apply_full_profile(profile, payload)

    if payload.is_complete:
        advance_deal_to(
            db,
            deal=current_deal,
            target_state=DealState.PROFILED,
            actor="buyer",
            reason="full_profile_completed",
        )
        advance_deal_to(
            db,
            deal=current_deal,
            target_state=DealState.MATCHING,
            actor="system",
            reason="matching_run_triggered",
        )
        run_matching(db, profile=profile, deal=current_deal, limit=10)

    db.commit()
    return ok({"message": "Profile updated", "version": profile.version})


@router.post("/profile/quick-match")
def post_quick_match(
    payload: QuickMatchRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    current_deal=Depends(get_current_deal),
) -> dict:
    profile = get_or_create_profile(db, current_user.id)
    apply_quick_match(profile, payload)

    advance_deal_to(
        db,
        deal=current_deal,
        target_state=DealState.MATCHING,
        actor="system",
        reason="quick_matching_run_triggered",
    )

    matches = run_matching(db, profile=profile, deal=current_deal, limit=10)
    db.commit()

    return ok(
        {
            "profile_tier": profile.profile_tier.value,
            "match_count": len(matches),
            "recommendations": [
                {
                    "vin": m.vin,
                    "score": m.match_score,
                    "explainability": m.explainability_text,
                    "market_retail": m.marketcheck_retail,
                    "estimated_otd": m.estimated_otd,
                    "danny_savings": m.danny_savings,
                }
                for m in matches
            ],
        }
    )


@router.get("/deal")
def get_deal(current_deal=Depends(get_current_deal)) -> dict:
    return ok(
        {
            "id": current_deal.id,
            "stage": current_deal.stage.value,
            "funding_state": current_deal.funding_state.value,
            "assigned_agent": current_deal.assigned_agent,
            "human_checkpoint_required": current_deal.human_checkpoint_required,
            "selected_vin": current_deal.selected_vin,
            "ghl_opportunity_id": current_deal.ghl_opportunity_id,
            "delivered_at": current_deal.delivered_at,
            "closed_at": current_deal.closed_at,
        }
    )


@router.get("/recommendations")
def get_recommendations(
    db: Session = Depends(get_db),
    current_deal=Depends(get_current_deal),
) -> dict:
    matches = db.scalars(
        select(VehicleMatch)
        .where(VehicleMatch.deal_id == current_deal.id)
        .order_by(VehicleMatch.match_score.desc())
    ).all()

    return ok(
        [
            {
                "vin": m.vin,
                "match_score": m.match_score,
                "explainability": m.explainability_text,
                "market_retail": m.marketcheck_retail,
                "target_acquisition": m.vehicle.price_asking if m.vehicle else None,
                "estimated_otd": m.estimated_otd,
                "danny_savings": m.danny_savings,
                "vehicle": {
                    "year": m.vehicle.year if m.vehicle else None,
                    "make": m.vehicle.make if m.vehicle else None,
                    "model": m.vehicle.model if m.vehicle else None,
                    "trim": m.vehicle.trim if m.vehicle else None,
                    "odometer": m.vehicle.odometer if m.vehicle else None,
                    "price": m.vehicle.price_asking if m.vehicle else None,
                    "location": f"{m.vehicle.location_state} {m.vehicle.location_zip}" if m.vehicle else None,
                    "images": m.vehicle.images if m.vehicle else [],
                },
            }
            for m in matches
        ]
    )


@router.post("/recommendations/{vin}/select")
def select_recommendation(
    vin: str,
    db: Session = Depends(get_db),
    current_deal=Depends(get_current_deal),
) -> dict:
    match = db.scalar(
        select(VehicleMatch).where(VehicleMatch.deal_id == current_deal.id, VehicleMatch.vin == vin)
    )
    if not match:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recommendation not found")

    match.status = "selected"
    current_deal.selected_vin = vin
    if current_deal.stage == DealState.MATCHING:
        transition_deal_state(
            db,
            deal=current_deal,
            new_state=DealState.VEHICLE_SELECTED,
            actor="buyer",
            reason="recommendation_selected",
            payload={"vin": vin},
        )

    db.commit()
    return ok({"vin": vin, "status": "selected"})


@router.post("/recommendations/{vin}/favorite")
def favorite_recommendation(
    vin: str,
    db: Session = Depends(get_db),
    current_deal=Depends(get_current_deal),
) -> dict:
    match = db.scalar(
        select(VehicleMatch).where(VehicleMatch.deal_id == current_deal.id, VehicleMatch.vin == vin)
    )
    if not match:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recommendation not found")

    match.status = "favorited"
    if match.vehicle:
        ensure_tier3_processing_job(
            db,
            vin=match.vehicle.vin,
            trigger_event="favorite_recommendation",
            source_image_urls=match.vehicle.images or [],
        )
    db.commit()
    return ok({"vin": vin, "status": "favorited"})


@router.get("/garage")
def get_garage(
    db: Session = Depends(get_db),
    current_deal=Depends(get_current_deal),
) -> dict:
    garage_items = db.scalars(
        select(GarageItem)
        .where(GarageItem.deal_id == current_deal.id)
        .where(GarageItem.status != "removed")
        .order_by(GarageItem.updated_at.desc())
    ).all()
    vehicles = {v.vin: v for v in db.scalars(select(Vehicle).where(Vehicle.vin.in_([item.vin for item in garage_items]))).all()}
    return ok(
        [
            _serialize_garage_item(db, item, vehicles.get(item.vin), deal_stage=current_deal.stage)
            for item in garage_items
        ]
    )


@router.post("/garage/{vin}")
def add_to_garage(
    vin: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    current_deal=Depends(get_current_deal),
) -> dict:
    normalized_vin = _normalize_vin(vin)
    vehicle = db.get(Vehicle, normalized_vin)
    if not vehicle:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vehicle not found in inventory")

    item = db.scalar(
        select(GarageItem).where(GarageItem.deal_id == current_deal.id, GarageItem.vin == normalized_vin)
    )
    if not item:
        item = GarageItem(
            deal_id=current_deal.id,
            user_id=current_user.id,
            vin=normalized_vin,
            status="saved",
            source="inventory",
        )
        db.add(item)
    else:
        item.status = "saved"

    _ensure_vehicle_match(
        db,
        deal_id=current_deal.id,
        user_id=current_user.id,
        vehicle=vehicle,
        status_value="favorited",
        explainability="Saved from inventory garage",
    )
    ensure_tier3_processing_job(
        db,
        vin=vehicle.vin,
        trigger_event="garage_saved",
        source_image_urls=vehicle.images or [],
    )

    db.commit()
    db.refresh(item)
    return ok(_serialize_garage_item(db, item, vehicle, deal_stage=current_deal.stage))


@router.delete("/garage/{vin}")
def remove_from_garage(
    vin: str,
    db: Session = Depends(get_db),
    current_deal=Depends(get_current_deal),
) -> dict:
    normalized_vin = _normalize_vin(vin)
    item = db.scalar(
        select(GarageItem).where(GarageItem.deal_id == current_deal.id, GarageItem.vin == normalized_vin)
    )
    if not item or item.status == "removed":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Garage item not found")

    item.status = "removed"
    db.commit()
    return ok({"vin": normalized_vin, "status": "removed"})


@router.post("/garage/{vin}/acquire")
def start_garage_acquisition(
    vin: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    current_deal=Depends(get_current_deal),
) -> dict:
    normalized_vin = _normalize_vin(vin)
    vehicle = db.get(Vehicle, normalized_vin)
    if not vehicle:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vehicle not found in inventory")

    item = db.scalar(
        select(GarageItem).where(GarageItem.deal_id == current_deal.id, GarageItem.vin == normalized_vin)
    )
    if not item:
        item = GarageItem(
            deal_id=current_deal.id,
            user_id=current_user.id,
            vin=normalized_vin,
            status="saved",
            source="inventory",
        )
        db.add(item)

    item.status = "acquisition_started"
    item.acquisition_started_at = datetime.now(UTC)

    _ensure_vehicle_match(
        db,
        deal_id=current_deal.id,
        user_id=current_user.id,
        vehicle=vehicle,
        status_value="selected",
        explainability="Selected from inventory garage",
    )
    selected_matches = db.scalars(
        select(VehicleMatch).where(
            VehicleMatch.deal_id == current_deal.id,
            VehicleMatch.status == "selected",
            VehicleMatch.vin != normalized_vin,
        )
    ).all()
    for match in selected_matches:
        match.status = "favorited"

    current_deal.selected_vin = normalized_vin

    if current_deal.stage in {
        DealState.LEAD,
        DealState.PRE_QUALIFYING,
        DealState.QUALIFIED,
        DealState.ENGAGED,
        DealState.PROFILED,
        DealState.MATCHING,
    }:
        advance_deal_to(
            db,
            deal=current_deal,
            target_state=DealState.VEHICLE_SELECTED,
            actor="buyer",
            reason="garage_vehicle_selected",
            payload={"vin": normalized_vin},
        )

    ensure_tier3_processing_job(
        db,
        vin=vehicle.vin,
        trigger_event="garage_acquisition_started",
        source_image_urls=vehicle.images or [],
    )

    db.commit()
    db.refresh(item)
    return ok(
        {
            "garage_item": _serialize_garage_item(db, item, vehicle, deal_stage=current_deal.stage),
            "deal": {
                "id": current_deal.id,
                "stage": current_deal.stage.value,
                "selected_vin": current_deal.selected_vin,
            },
        }
    )


@router.get("/documents")
def get_documents(
    db: Session = Depends(get_db),
    current_deal=Depends(get_current_deal),
) -> dict:
    docs = db.scalars(select(Document).where(Document.deal_id == current_deal.id)).all()
    return ok(
        [
            {
                "id": d.id,
                "doc_type": d.doc_type,
                "status": d.status,
                "signer_role": d.signer_role,
                "signed_at": d.signed_at,
            }
            for d in docs
        ]
    )


@router.get("/delivery")
def get_delivery(
    db: Session = Depends(get_db),
    current_deal=Depends(get_current_deal),
) -> dict:
    shipment = db.scalar(select(Shipment).where(Shipment.deal_id == current_deal.id))
    if not shipment:
        return ok({"status": "not_scheduled"})
    return ok(
        {
            "status": shipment.status,
            "tracking_url": shipment.tracking_url,
            "eta": shipment.eta,
            "delivered_at": shipment.delivered_at,
        }
    )


@router.post("/return/initiate")
def post_return_initiate(
    payload: InitiateReturnRequest,
    db: Session = Depends(get_db),
    current_deal=Depends(get_current_deal),
) -> dict:
    return_case = initiate_return(
        db,
        deal=current_deal,
        reason=payload.reason,
        buyer_transport_responsibility=payload.buyer_transport_responsibility,
    )
    db.commit()
    return ok(
        {
            "return_case_id": return_case.id,
            "return_state": return_case.return_state.value,
            "initiated_at": return_case.initiated_at,
        }
    )


@router.get("/notifications")
def get_notifications(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    notifications = db.scalars(
        select(Notification)
        .where(Notification.user_id == current_user.id)
        .order_by(Notification.created_at.desc())
        .limit(100)
    ).all()
    return ok(
        [
            {
                "id": n.id,
                "message": n.message,
                "channel": n.channel,
                "is_read": n.is_read,
                "created_at": n.created_at,
            }
            for n in notifications
        ]
    )
