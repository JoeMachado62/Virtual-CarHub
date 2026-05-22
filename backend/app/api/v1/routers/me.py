import logging
from datetime import UTC, datetime
from hashlib import sha256
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_deal, get_current_user, is_admin_user
from app.core.config import settings
from app.core.constants import AuctionPlatform, DealState, FundingState, ImageTier, InventorySourceType, OveDetailRequestStatus
from app.core.responses import ok
from app.db.session import get_db
from app.models.entities import AuditEvent, Document, GarageItem, Notification, OveDetailRequest, OveVehicleDetail, Shipment, User, Vehicle, VehicleHistoryEnrichment, VehicleImageAsset, VehicleMatch
from app.schemas.profile import ProfileUpdateRequest, QuickMatchRequest
from app.schemas.returns import InitiateReturnRequest
from app.schemas.ove_inventory import OveDetailRequestEnqueueRequest
from app.services.audit_service import log_event
from app.services.deal_service import advance_deal_for_trigger
from app.services.image_pipeline_service import (
    _asset_url,
    canonical_source_image_url,
    ensure_tier3_processing_job,
    resolve_vehicle_card_media,
    resolve_vehicle_display_context,
    sanitize_marketcheck_photo_urls,
    sync_marketcheck_source_assets,
)
from app.services.marketcheck_history_enrichment_service import (
    build_marketcheck_client,
    extract_listing_metadata,
    select_best_history_entry,
)
from app.services.vehicle_image_screening_service import SCREENING_VERSION, screen_marketcheck_vehicle_images
from app.services.ghl_lifecycle_service import GHLLifecycleService
from app.services.matching_service import run_matching
from app.services.ove_inventory_service import enqueue_ove_detail_request
from app.services.photo_access_service import can_view_protected_vehicle_photos
from app.services.profile_service import apply_full_profile, apply_quick_match, get_or_create_profile
from app.services.return_service import initiate_return
from app.services.notification_service import create_notification
from app.services.s3_service import cache_remote_image, object_storage_uploads_enabled

router = APIRouter()
logger = logging.getLogger(__name__)

VCH_MARGIN = 1500.0
AUCTION_BUY_FEE_UNDER_50K = 1000.0
AUCTION_BUY_FEE_OVER_50K = 1300.0
DETAIL_SHOP_FEE = 150.0
MARKETING_FEE = 599.0

CONDITION_REPORT_ELIGIBLE_FUNDING_STATES = {
    FundingState.PRE_APPROVED,
    FundingState.TERMS_ACCEPTED,
    FundingState.FINAL_APPROVAL_PENDING,
    FundingState.FULLY_FUNDED,
    FundingState.CASH_BUYER,
}

SURPLUS_CONDITION_REPORT_MESSAGE = (
    'Vehicles sourced from surplus inventory channels are aged inventory units that are currently rated as "Retail Ready". '
    'Because they have been thru a dealers service shop and reconditioning process we only offer these "AS IS" . '
    "That said, we highly recommend a professional inspection. Contracting an inspector or hiring a mechanic to do this can cost from $150 to $200+  "
    'That is why Virtual CarHub has partnered with "Wrench" the largest mobile mechanic company in the U.S. '
    "You can order a full condition report performed by an ASE certified mechanic for only $99 today. "
    "Just click on the ORDER REPORT button below."
)

SURPLUS_SOURCE_TYPES = {
    InventorySourceType.MARKETCHECK.value,
    InventorySourceType.DEALER_WHOLESALE.value,
    InventorySourceType.DEALER_PARTNER.value,
    "wholesale",
}


class MarkNotificationsReadRequest(BaseModel):
    ids: list[str] | None = None


class PublishSurplusImagesRequest(BaseModel):
    image_urls: list[str]

def _normalize_vin(vin: str) -> str:
    normalized = vin.strip().upper()
    if len(normalized) != 17:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="VIN must be 17 characters")
    return normalized


def _resolve_vehicle_or_404(db: Session, identifier: str) -> Vehicle:
    """Accept either a VIN or a public slug and return the Vehicle row.

    Raises 404 if nothing matches. Callers should use ``vehicle.vin`` as
    the canonical key for any downstream lookups (garage items, deals,
    etc.) since those tables key off the raw VIN.
    """
    from app.services.vin_slug_service import resolve_vehicle_identifier

    vehicle = resolve_vehicle_identifier(db, identifier)
    if not vehicle:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vehicle not found in inventory")
    return vehicle


def _condition_report_eligibility(deal, user) -> tuple[bool, str]:
    if isinstance(user, User) and is_admin_user(user):
        return True, "Eligible to request a VCH condition report (admin)."

    # Check if user has manual pre-approval override. Guard against the
    # helper being called with an unresolved FastAPI ``Depends`` marker
    # (happens when route handlers are invoked directly without FastAPI
    # resolving their default parameters, e.g. from tests).
    if isinstance(user, User) and user.is_preapproved:
        # Check if pre-approval hasn't expired
        if user.preapproved_until and user.preapproved_until < datetime.now(UTC):
            return False, "Pre-approval has expired. Please contact support to renew."
        return True, "Eligible to request a VCH condition report (pre-approved buyer)."

    # Check standard funding state eligibility
    if deal.funding_state in CONDITION_REPORT_ELIGIBLE_FUNDING_STATES:
        return True, "Eligible to request a VCH condition report."

    return False, "Condition/inspection report requests require a pre-approved buyer account."


def _is_surplus_inventory(vehicle: Vehicle) -> bool:
    return (vehicle.source_type or "").strip().lower() in SURPLUS_SOURCE_TYPES


def _vehicle_title(vehicle: Vehicle) -> str:
    title = " ".join(
        str(part).strip()
        for part in (vehicle.year, vehicle.make, vehicle.model, vehicle.trim)
        if part not in (None, "")
    )
    return title or vehicle.vin


def _advertised_price(base_price: float | None) -> float | None:
    if base_price is None:
        return None
    buy_fee = AUCTION_BUY_FEE_UNDER_50K if base_price <= 50000 else AUCTION_BUY_FEE_OVER_50K
    return round(float(base_price) + buy_fee + DETAIL_SHOP_FEE + VCH_MARGIN + MARKETING_FEE, 2)


def _image_urls_from_marketcheck_listing(payload: dict | None) -> list[str]:
    listing = payload or {}
    metadata = extract_listing_metadata(listing)
    urls = list(metadata.get("supplemental_photo_links") or [])
    media = listing.get("media") if isinstance(listing.get("media"), dict) else {}
    for key in ("photo_links_cached", "photo_links", "photos", "images"):
        value = media.get(key) if isinstance(media, dict) else None
        if isinstance(value, list):
            urls.extend(str(item) for item in value if item)
    for key in ("photo_links", "photo_links_cached", "image_urls", "images"):
        value = listing.get(key)
        if isinstance(value, list):
            urls.extend(str(item) for item in value if item)
    return sanitize_marketcheck_photo_urls(urls)


def _load_marketcheck_asset_urls(db: Session, vin: str, *, active_only: bool = True) -> list[str]:
    query = select(VehicleImageAsset).where(
        VehicleImageAsset.vin == vin,
        VehicleImageAsset.tier == ImageTier.SOURCE_CACHE,
        VehicleImageAsset.source_kind == "marketcheck",
    )
    if active_only:
        query = query.where(VehicleImageAsset.active.is_(True))
    assets = db.scalars(
        query
        .order_by(
            VehicleImageAsset.is_primary.desc(),
            VehicleImageAsset.display_order.asc(),
            VehicleImageAsset.created_at.asc(),
        )
    ).all()
    return [url for asset in assets if (url := asset.external_url)]


def _load_admin_hidden_marketcheck_asset_urls(db: Session, vin: str) -> list[str]:
    assets = db.scalars(
        select(VehicleImageAsset)
        .where(
            VehicleImageAsset.vin == vin,
            VehicleImageAsset.tier == ImageTier.SOURCE_CACHE,
            VehicleImageAsset.source_kind == "marketcheck",
            VehicleImageAsset.active.is_(False),
        )
        .order_by(VehicleImageAsset.display_order.asc(), VehicleImageAsset.created_at.asc())
    ).all()
    out: list[str] = []
    for asset in assets:
        screening = (asset.metadata_json or {}).get("overlay_screening")
        if not isinstance(screening, dict) or screening.get("approved") is not False:
            continue
        if url := _asset_url(asset):
            out.append(url)
    return out


def _prepare_surplus_condition_report_images(db: Session, vehicle: Vehicle, *, include_hidden: bool = False) -> tuple[list[str], list[str], int]:
    candidate_urls: list[str] = []
    candidate_urls.extend(str(url) for url in (vehicle.images or []) if url)
    candidate_urls.extend(_load_marketcheck_asset_urls(db, vehicle.vin, active_only=False))

    record = db.get(VehicleHistoryEnrichment, vehicle.vin)
    if record:
        metadata = record.listing_metadata_json or {}
        candidate_urls.extend(str(url) for url in (metadata.get("supplemental_photo_links") or []) if url)
        candidate_urls.extend(_image_urls_from_marketcheck_listing(record.listing_payload_json or {}))
        candidate_urls.extend(_image_urls_from_marketcheck_listing(record.history_entry_json or {}))

    listing_id: str | None = record.source_listing_id if record else None
    has_local_image_candidates = bool(sanitize_marketcheck_photo_urls(candidate_urls))
    if settings.has_marketcheck and not has_local_image_candidates:
        try:
            client = build_marketcheck_client()
            history_payload = client.get_history(vehicle.vin)
            entry = select_best_history_entry(history_payload, preferred_source_url=vehicle.source_url)
            listing_payload = entry or {}
            listing_id = str((entry or {}).get("id") or (entry or {}).get("listing_id") or listing_id or "").strip() or None
            if listing_id:
                try:
                    detailed_listing = client.get_listing(listing_id)
                    if isinstance(detailed_listing, dict):
                        listing_payload = detailed_listing
                except Exception:
                    logger.info("surplus_marketcheck_listing_fetch_failed vin=%s listing_id=%s", vehicle.vin, listing_id, exc_info=True)
            if isinstance(listing_payload, dict):
                candidate_urls.extend(_image_urls_from_marketcheck_listing(listing_payload))
        except Exception:
            logger.info("surplus_marketcheck_history_fetch_failed vin=%s", vehicle.vin, exc_info=True)

    sanitized = sanitize_marketcheck_photo_urls(candidate_urls)
    if sanitized:
        sync_marketcheck_source_assets(
            db,
            vin=vehicle.vin,
            listing_id=listing_id,
            image_urls=sanitized,
        )
        db.flush()
        sanitized = sanitize_marketcheck_photo_urls(_load_marketcheck_asset_urls(db, vehicle.vin, active_only=False) or sanitized)
        sanitized = screen_marketcheck_vehicle_images(db, vin=vehicle.vin, image_urls=sanitized)
        db.flush()

    hidden = _load_admin_hidden_marketcheck_asset_urls(db, vehicle.vin) if include_hidden else []
    return sanitized, hidden, max(0, len([url for url in candidate_urls if url]) - len(sanitized))


def _cache_ordered_surplus_marketcheck_images(db: Session, vin: str) -> int:
    """Copy ordered surplus source photos to object storage when configured.

    SOURCE_CACHE assets keep the original MarketCheck/dealer URL as provenance,
    while storage_key points at our durable copy for future display. This is
    deliberately best-effort: a CDN timeout should not block a buyer's CR order.
    """
    if not object_storage_uploads_enabled():
        return 0

    assets = db.scalars(
        select(VehicleImageAsset)
        .where(
            VehicleImageAsset.vin == vin,
            VehicleImageAsset.tier == ImageTier.SOURCE_CACHE,
            VehicleImageAsset.source_kind == "marketcheck",
        )
        .order_by(VehicleImageAsset.display_order.asc(), VehicleImageAsset.created_at.asc())
    ).all()
    cached_count = 0
    for asset in assets:
        if asset.storage_key or not asset.external_url:
            continue
        source_url = str(asset.external_url).strip()
        if not source_url:
            continue
        key = _surplus_marketcheck_storage_key(vin=vin, source_url=source_url, display_order=asset.display_order)
        try:
            result = cache_remote_image(source_url=source_url, key=key, timeout_seconds=15.0)
        except Exception:
            logger.info("surplus_marketcheck_image_cache_failed vin=%s url=%s", vin, source_url, exc_info=True)
            metadata = dict(asset.metadata_json or {})
            metadata["surplus_source_cache_error_at"] = datetime.now(UTC).isoformat()
            asset.metadata_json = metadata
            continue
        asset.storage_key = result.storage_key
        asset.sha256 = result.sha256
        metadata = dict(asset.metadata_json or {})
        metadata.update(
            {
                "surplus_source_cached_at": datetime.now(UTC).isoformat(),
                "surplus_source_cache_bucket": result.bucket,
                "surplus_source_cache_content_type": result.content_type,
                "surplus_source_cache_size_bytes": result.size_bytes,
            }
        )
        asset.metadata_json = metadata
        cached_count += 1
    return cached_count


def _surplus_marketcheck_storage_key(*, vin: str, source_url: str, display_order: int) -> str:
    digest = sha256(canonical_source_image_url(source_url).encode("utf-8")).hexdigest()
    extension = _image_extension_from_url(source_url)
    return f"source-cache/{vin}/marketcheck/{display_order:03d}-{digest[:16]}{extension}"


def _image_extension_from_url(url: str) -> str:
    path = urlsplit(str(url)).path.lower()
    for extension in (".jpg", ".jpeg", ".png", ".webp", ".avif"):
        if path.endswith(extension):
            return ".jpg" if extension == ".jpeg" else extension
    return ".jpg"


def _infer_auction_platform(vehicle: Vehicle, ove_detail: OveVehicleDetail | None) -> AuctionPlatform:
    if ove_detail:
        return ove_detail.source_platform

    source_url = (vehicle.source_url or "").lower()
    if "openlane" in source_url:
        return AuctionPlatform.OPENLANE
    if "ally" in source_url:
        return AuctionPlatform.ALLY_SMART_AUCTION
    return AuctionPlatform.MANHEIM


def _enqueue_auction_detail_refresh(
    db: Session,
    *,
    vehicle: Vehicle,
    current_deal,
    current_user: User,
    ove_detail: OveVehicleDetail | None = None,
    priority: int,
    reason: str,
) -> tuple[dict[str, str | bool] | None, AuctionPlatform | None]:
    if vehicle.source_type not in {InventorySourceType.OVE.value, InventorySourceType.AUCTION.value}:
        return None, None

    source_platform = _infer_auction_platform(vehicle, ove_detail)
    request, deduplicated = enqueue_ove_detail_request(
        db,
        vin=vehicle.vin,
        payload=OveDetailRequestEnqueueRequest(
            source_platform=source_platform,
            priority=priority,
            request_source="buyer_portal",
            requested_by=current_user.email or current_user.id,
            reason=reason,
            metadata={
                "deal_id": current_deal.id,
                "user_id": current_user.id,
                "selected_vin": current_deal.selected_vin == vehicle.vin,
            },
        ),
    )
    return {
        "queued": True,
        "deduplicated": deduplicated,
        "request_id": request.id,
        "status": request.status.value,
    }, source_platform


def _serialize_garage_item(
    db: Session,
    item: GarageItem,
    vehicle: Vehicle | None,
    *,
    deal_stage: DealState,
    allow_protected_photos: bool,
    cr_request_status: str | None = None,
) -> dict:
    if vehicle:
        media = resolve_vehicle_card_media(
            db,
            vehicle=vehicle,
            deal_stage=deal_stage,
            deal_id=item.deal_id,
            is_garage_view=True,
            allow_protected_photos=allow_protected_photos,
        )
        display_context = resolve_vehicle_display_context(
            db,
            vehicle=vehicle,
            deal_stage=deal_stage,
            deal_id=item.deal_id,
            is_garage_view=True,
            allow_protected_photos=allow_protected_photos,
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
        "public_slug": vehicle.public_slug if vehicle else None,
        "status": item.status,
        "source": item.source,
        "added_at": item.created_at,
        "updated_at": item.updated_at,
        "acquisition_started_at": item.acquisition_started_at,
        "deal_stage": deal_stage.value,
        "display_mode": display_mode,
        "inspection_status": inspection_status,
        "has_inspection_report": has_inspection_report,
        "cr_request_status": cr_request_status,
        "display_context": display_context,
        "vehicle": {
            "year": vehicle.year if vehicle else None,
            "make": vehicle.make if vehicle else None,
            "model": vehicle.model if vehicle else None,
            "trim": vehicle.trim if vehicle else None,
            "price_asking": _advertised_price(vehicle.price_asking) if vehicle else None,
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


def _serialize_recommendation(db: Session, match: VehicleMatch) -> dict:
    vehicle = match.vehicle
    display_context = (
        resolve_vehicle_display_context(db, vehicle=vehicle)
        if vehicle
        else {}
    )
    hero_image = display_context.get("hero_image") if display_context.get("has_chromedata_stock") else None
    return {
        "vin": match.vin,
        "public_slug": vehicle.public_slug if vehicle else None,
        "status": match.status,
        "match_score": match.match_score,
        "explainability": match.explainability_text,
        "market_retail": match.marketcheck_retail,
        "target_acquisition": vehicle.price_asking if vehicle else None,
        "estimated_otd": match.estimated_otd,
        "danny_savings": match.danny_savings,
        "last_seen_active": vehicle.last_seen_active if vehicle else None,
        "vehicle": {
            "year": vehicle.year if vehicle else None,
            "make": vehicle.make if vehicle else None,
            "model": vehicle.model if vehicle else None,
            "trim": vehicle.trim if vehicle else None,
            "odometer": vehicle.odometer if vehicle else None,
            "price": vehicle.price_asking if vehicle else None,
            "location": f"{vehicle.location_state} {vehicle.location_zip}" if vehicle else None,
            "images": [hero_image] if hero_image else [],
            "thumbnail": hero_image,
        },
    }


def _ensure_recommendation_chromedata_assets(db: Session, matches: list[VehicleMatch], *, limit: int = 4) -> None:
    if not settings.has_chromedata_media:
        return

    from app.services.chromedata_service import build_chromedata_manifest, sync_chromedata_source_assets

    synced = False
    for match in matches[:limit]:
        vehicle = match.vehicle
        if not vehicle:
            continue
        existing_cd = db.scalar(
            select(VehicleImageAsset.id).where(
                VehicleImageAsset.vin == vehicle.vin,
                VehicleImageAsset.source_kind == "chromedata",
                VehicleImageAsset.active == True,  # noqa: E712
            ).limit(1)
        )
        if existing_cd:
            continue
        try:
            manifest = build_chromedata_manifest(vehicle, detail_level="card")
            if manifest:
                sync_chromedata_source_assets(db, vehicle=vehicle, manifest=manifest)
                synced = True
        except Exception:
            logger.debug("ChromeData recommendation sync failed for vin=%s", vehicle.vin, exc_info=True)

    if synced:
        db.commit()


@router.get("/profile")
def get_profile(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    profile = get_or_create_profile(db, current_user.id)
    db.commit()
    return ok(
        {
            "first_name": current_user.first_name,
            "last_name": current_user.last_name,
            "profile_tier": profile.profile_tier.value,
            "version": profile.version,
            "bfv_json": profile.bfv_json,
            "intake_steps_complete": profile.intake_steps_complete,
            "hard_constraints": profile.hard_constraints,
            "demographics": profile.demographics,
            "is_complete": profile.is_complete,
        }
    )


@router.get("/account-status")
def get_account_status(
    current_user: User = Depends(get_current_user),
    current_deal=Depends(get_current_deal),
) -> dict:
    """Lightweight account-state lookup used by the frontend to decide
    whether to reveal sensitive data like full VINs. Returns whether the
    buyer is currently pre-qualified (either via manual admin override or
    an active deal in a funding state that grants protected access)."""
    is_preapproved = can_view_protected_vehicle_photos(user=current_user, deal=current_deal)
    return ok(
        {
            "is_preapproved": is_preapproved,
            "user_id": current_user.id,
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
        advance_deal_for_trigger(db, deal=current_deal, trigger="full_profile_completed")
        advance_deal_for_trigger(db, deal=current_deal, trigger="matching_run_triggered")
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

    advance_deal_for_trigger(db, deal=current_deal, trigger="quick_matching_run_triggered")

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
def get_deal(current_user: User = Depends(get_current_user), current_deal=Depends(get_current_deal)) -> dict:
    condition_report_eligible, condition_report_reason = _condition_report_eligibility(current_deal, current_user)
    return ok(
        {
            "id": current_deal.id,
            "stage": current_deal.stage.value,
            "funding_state": current_deal.funding_state.value,
            "condition_report_eligible": condition_report_eligible,
            "condition_report_eligibility_reason": condition_report_reason,
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
    _ensure_recommendation_chromedata_assets(db, matches)

    return ok([_serialize_recommendation(db, m) for m in matches])


@router.post("/recommendations/refresh")
def refresh_recommendations(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    current_deal=Depends(get_current_deal),
) -> dict:
    profile = get_or_create_profile(db, current_user.id)
    if profile.is_complete and profile.bfv_json:
        run_matching(db, profile=profile, deal=current_deal, limit=10)
        db.commit()

    matches = db.scalars(
        select(VehicleMatch)
        .where(VehicleMatch.deal_id == current_deal.id)
        .order_by(VehicleMatch.match_score.desc())
    ).all()
    _ensure_recommendation_chromedata_assets(db, matches)
    return ok([_serialize_recommendation(db, m) for m in matches])


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
    selected_matches = db.scalars(
        select(VehicleMatch).where(
            VehicleMatch.deal_id == current_deal.id,
            VehicleMatch.status == "selected",
            VehicleMatch.vin != vin,
        )
    ).all()
    for selected_match in selected_matches:
        selected_match.status = "favorited"

    current_deal.selected_vin = vin
    if match.vehicle:
        item = db.scalar(select(GarageItem).where(GarageItem.deal_id == current_deal.id, GarageItem.vin == vin))
        if not item:
            item = GarageItem(
                deal_id=current_deal.id,
                user_id=current_deal.user_id,
                vin=vin,
                status="saved",
                source="recommendation",
            )
            db.add(item)
        elif item.status == "removed":
            item.status = "saved"
            item.source = "recommendation"
        ensure_tier3_processing_job(
            db,
            vin=match.vehicle.vin,
            trigger_event="recommendation_selected",
            source_image_urls=match.vehicle.images or [],
        )
    advance_deal_for_trigger(
        db,
        deal=current_deal,
        trigger="recommendation_selected",
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
    current_user: User = Depends(get_current_user),
    current_deal=Depends(get_current_deal),
) -> dict:
    garage_items = db.scalars(
        select(GarageItem)
        .where(GarageItem.deal_id == current_deal.id)
        .where(GarageItem.status != "removed")
        .order_by(GarageItem.updated_at.desc())
    ).all()
    garage_vins = [item.vin for item in garage_items]
    vehicles = {v.vin: v for v in db.scalars(select(Vehicle).where(Vehicle.vin.in_(garage_vins))).all()}
    allow_protected_photos = can_view_protected_vehicle_photos(user=current_user, deal=current_deal)

    # Batch-query the most recent OveDetailRequest per garage VIN so the
    # frontend can restore "CR Pending" / "CR Failed" state across reloads.
    _ACTIVE_CR_STATUSES = (
        OveDetailRequestStatus.PENDING,
        OveDetailRequestStatus.CLAIMED,
        OveDetailRequestStatus.IN_PROGRESS,
        OveDetailRequestStatus.FAILED,
    )
    cr_requests = db.execute(
        select(OveDetailRequest.vin, OveDetailRequest.status)
        .where(OveDetailRequest.vin.in_(garage_vins))
        .where(OveDetailRequest.request_source == "buyer_portal")
        .order_by(OveDetailRequest.requested_at.desc())
    ).all()
    # Keep the latest request per VIN — map to a simplified status string.
    cr_status_by_vin: dict[str, str | None] = {}
    for vin, req_status in cr_requests:
        if vin in cr_status_by_vin:
            continue  # already recorded the most-recent request
        if req_status in _ACTIVE_CR_STATUSES:
            cr_status_by_vin[vin] = "pending"
        elif req_status == OveDetailRequestStatus.TERMINAL:
            cr_status_by_vin[vin] = "terminal"
        # COMPLETED / CANCELED → no flag needed (has_inspection_report covers it)

    surplus_events = db.scalars(
        select(AuditEvent)
        .where(AuditEvent.deal_id == current_deal.id)
        .where(AuditEvent.event_type == "buyer_surplus_condition_report_ordered")
        .order_by(AuditEvent.timestamp.desc())
        .limit(200)
    ).all()
    for event in surplus_events:
        vin = str((event.payload_json or {}).get("vin") or "").strip().upper()
        if vin and vin in garage_vins and vin not in cr_status_by_vin:
            cr_status_by_vin[vin] = "pending"

    return ok(
        [
            _serialize_garage_item(
                db,
                item,
                vehicles.get(item.vin),
                deal_stage=current_deal.stage,
                allow_protected_photos=allow_protected_photos,
                cr_request_status=cr_status_by_vin.get(item.vin),
            )
            for item in garage_items
        ]
    )


@router.post("/garage/{identifier}")
def add_to_garage(
    identifier: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    current_deal=Depends(get_current_deal),
) -> dict:
    vehicle = _resolve_vehicle_or_404(db, identifier)
    normalized_vin = vehicle.vin

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
        source_image_urls=[] if _is_surplus_inventory(vehicle) else (vehicle.images or []),
    )

    # NOTE: Do NOT enqueue an auction detail refresh here.  The OVE detail
    # refresh also triggers condition-report scraping, which should only happen
    # when the buyer explicitly clicks "Request CR".  Previously an
    # _enqueue_auction_detail_refresh() call here caused CRs to appear
    # "instantly" because the scrape had already been kicked off on garage-add.

    db.commit()
    db.refresh(item)
    return ok(
        {
            "garage_item": _serialize_garage_item(
                db,
                item,
                vehicle,
                deal_stage=current_deal.stage,
                allow_protected_photos=can_view_protected_vehicle_photos(user=current_user, deal=current_deal),
            ),
            "dealer_photos_fetched": 0,
        }
    )


@router.post("/vehicles/{identifier}/surplus-condition-report-preview")
def preview_surplus_condition_report(
    identifier: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    current_deal=Depends(get_current_deal),
) -> dict:
    eligible, reason = _condition_report_eligibility(current_deal, current_user)
    if not eligible:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=reason)

    vehicle = _resolve_vehicle_or_404(db, identifier)
    if not _is_surplus_inventory(vehicle):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Surplus condition report requests are only supported for surplus inventory.",
        )

    existing_garage = db.scalar(
        select(GarageItem).where(GarageItem.deal_id == current_deal.id, GarageItem.vin == vehicle.vin)
    )
    if not existing_garage:
        db.add(GarageItem(
            deal_id=current_deal.id,
            user_id=current_user.id,
            vin=vehicle.vin,
            status="saved",
            source="surplus_condition_report_preview",
        ))
        db.flush()

    include_hidden = is_admin_user(current_user)
    images, hidden_images, removed_count = _prepare_surplus_condition_report_images(
        db,
        vehicle,
        include_hidden=include_hidden,
    )
    db.commit()

    payload = {
        "vin": vehicle.vin,
        "title": _vehicle_title(vehicle),
        "report_type": "surplus_wrench",
        "order_price": 99,
        "currency": "USD",
        "message": SURPLUS_CONDITION_REPORT_MESSAGE,
        "images": images,
    }
    if include_hidden:
        payload["hidden_images"] = hidden_images
        payload["removed_image_count"] = removed_count
    return ok(payload)


@router.post("/vehicles/{identifier}/surplus-condition-report-order")
def order_surplus_condition_report(
    identifier: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    current_deal=Depends(get_current_deal),
) -> dict:
    eligible, reason = _condition_report_eligibility(current_deal, current_user)
    if not eligible:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=reason)

    vehicle = _resolve_vehicle_or_404(db, identifier)
    if not _is_surplus_inventory(vehicle):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Surplus condition report orders are only supported for surplus inventory.",
        )

    images, _hidden_images, removed_count = _prepare_surplus_condition_report_images(db, vehicle)
    cached_image_count = _cache_ordered_surplus_marketcheck_images(db, vehicle.vin)
    log_event(
        db,
        deal_id=current_deal.id,
        event_type="buyer_surplus_condition_report_ordered",
        actor="buyer",
        payload={
            "vin": vehicle.vin,
            "user_id": current_user.id,
            "source_type": vehicle.source_type,
            "vendor": "wrench",
            "price": 99,
            "currency": "USD",
            "image_count": len(images),
            "removed_image_count": removed_count,
            "cached_image_count": cached_image_count,
        },
    )
    create_notification(
        db,
        user_id=current_user.id,
        deal_id=current_deal.id,
        message=f"Surplus inspection report ordered for {_vehicle_title(vehicle)}. We will update My Garage when it is ready.",
    )
    db.commit()

    return ok(
        {
            "vin": vehicle.vin,
            "status": "requested",
            "vendor": "wrench",
            "order_price": 99,
            "message": "Surplus inspection report ordered. We will update My Garage when it is ready.",
        }
    )


@router.post("/vehicles/{identifier}/surplus-condition-report-images/publish")
def publish_surplus_condition_report_images(
    identifier: str,
    payload: PublishSurplusImagesRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    if not is_admin_user(current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required.")

    vehicle = _resolve_vehicle_or_404(db, identifier)
    if not _is_surplus_inventory(vehicle):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Surplus image publishing is only supported for surplus inventory.",
        )

    requested_keys = {
        canonical_source_image_url(url)
        for url in payload.image_urls
        if str(url).strip()
    }
    if not requested_keys:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Select at least one image.")

    assets = db.scalars(
        select(VehicleImageAsset).where(
            VehicleImageAsset.vin == vehicle.vin,
            VehicleImageAsset.tier == ImageTier.SOURCE_CACHE,
            VehicleImageAsset.source_kind == "marketcheck",
        )
    ).all()
    published: list[str] = []
    now = datetime.now(UTC).isoformat()
    for asset in assets:
        key = canonical_source_image_url(asset.external_url or "")
        if key not in requested_keys:
            continue
        metadata = dict(asset.metadata_json or {})
        screening = dict(metadata.get("overlay_screening") or {})
        screening.update(
            {
                "version": SCREENING_VERSION,
                "provider": "admin",
                "model": "manual_override",
                "classification": "clean_vehicle_photo",
                "has_overlay": False,
                "approved": True,
                "admin_override": True,
                "admin_override_by": current_user.email,
                "admin_override_at": now,
                "reason": "Approved for public surplus report gallery by admin review.",
            }
        )
        metadata["overlay_screening"] = screening
        asset.metadata_json = metadata
        asset.active = True
        published_url = _asset_url(asset)
        if published_url:
            published.append(published_url)

    db.commit()
    return ok({"vin": vehicle.vin, "published_images": published, "published_count": len(published)})


@router.post("/vehicles/{identifier}/condition-report-request")
def request_vehicle_condition_report(
    identifier: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    current_deal=Depends(get_current_deal),
) -> dict:
    eligible, reason = _condition_report_eligibility(current_deal, current_user)
    if not eligible:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=reason)

    vehicle = _resolve_vehicle_or_404(db, identifier)
    normalized_vin = vehicle.vin

    # Auto-add vehicle to garage if not already present. Surplus Wrench
    # previews use this same shared request endpoint from the VDP.
    existing_garage = db.scalar(
        select(GarageItem).where(GarageItem.deal_id == current_deal.id, GarageItem.vin == normalized_vin)
    )
    if not existing_garage:
        db.add(GarageItem(
            deal_id=current_deal.id,
            user_id=current_user.id,
            vin=normalized_vin,
            status="saved",
            source="condition_report_request",
        ))
        db.flush()

    if _is_surplus_inventory(vehicle):
        include_hidden = is_admin_user(current_user)
        images, hidden_images, removed_count = _prepare_surplus_condition_report_images(
            db,
            vehicle,
            include_hidden=include_hidden,
        )
        response = {
            "vin": normalized_vin,
            "eligible": True,
            "report_type": "surplus_wrench",
            "title": _vehicle_title(vehicle),
            "order_price": 99,
            "currency": "USD",
            "message": SURPLUS_CONDITION_REPORT_MESSAGE,
            "images": images,
        }
        if include_hidden:
            response["hidden_images"] = hidden_images
            response["removed_image_count"] = removed_count
        log_event(
            db,
            deal_id=current_deal.id,
            event_type="buyer_surplus_condition_report_previewed",
            actor="buyer",
            payload={**response, "user_id": current_user.id, "source_type": vehicle.source_type},
        )
        db.commit()
        return ok(response)

    if vehicle.source_type not in {InventorySourceType.OVE.value, InventorySourceType.AUCTION.value}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Condition report requests are only supported for auction inventory.",
        )

    ove_detail = db.get(OveVehicleDetail, normalized_vin)
    if ove_detail and ove_detail.condition_report_json:
        response = {
            "vin": normalized_vin,
            "eligible": True,
            "already_available": True,
            "queued": False,
            "request_id": None,
            "status": "available",
            "message": "Condition report already available.",
        }
        log_event(
            db,
            deal_id=current_deal.id,
            event_type="buyer_condition_report_requested",
            actor="buyer",
            payload={**response, "user_id": current_user.id},
        )
        db.commit()
        return ok(response)

    ove_refresh, source_platform = _enqueue_auction_detail_refresh(
        db,
        vehicle=vehicle,
        current_deal=current_deal,
        current_user=current_user,
        ove_detail=ove_detail,
        priority=200 if current_deal.selected_vin == normalized_vin else 100,
        reason=f"buyer_condition_report_request:{current_deal.id}",
    )
    assert ove_refresh is not None

    response = {
        "vin": normalized_vin,
        "eligible": True,
        "already_available": False,
        **ove_refresh,
        "message": (
            "Condition report request already in progress."
            if ove_refresh["deduplicated"]
            else "Condition report requested. We will refresh the listing when it is ready."
        ),
    }
    log_event(
        db,
        deal_id=current_deal.id,
        event_type="buyer_condition_report_requested",
        actor="buyer",
        payload={
            **response,
            "user_id": current_user.id,
            "source_platform": source_platform.value,
        },
    )
    try:
        GHLLifecycleService().record_condition_report_requested(
            user=current_user,
            deal=current_deal,
            vin=normalized_vin,
        )
    except Exception:
        pass
    db.commit()
    return ok(response)


@router.delete("/garage/{identifier}")
def remove_from_garage(
    identifier: str,
    db: Session = Depends(get_db),
    current_deal=Depends(get_current_deal),
) -> dict:
    vehicle = _resolve_vehicle_or_404(db, identifier)
    normalized_vin = vehicle.vin
    item = db.scalar(
        select(GarageItem).where(GarageItem.deal_id == current_deal.id, GarageItem.vin == normalized_vin)
    )
    if not item or item.status == "removed":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Garage item not found")

    item.status = "removed"
    db.commit()
    return ok({"vin": normalized_vin, "status": "removed"})


@router.post("/garage/{identifier}/acquire")
def start_garage_acquisition(
    identifier: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    current_deal=Depends(get_current_deal),
) -> dict:
    vehicle = _resolve_vehicle_or_404(db, identifier)
    normalized_vin = vehicle.vin

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

    advance_deal_for_trigger(
        db,
        deal=current_deal,
        trigger="garage_vehicle_selected",
        payload={"vin": normalized_vin},
    )

    ensure_tier3_processing_job(
        db,
        vin=vehicle.vin,
        trigger_event="garage_acquisition_started",
        source_image_urls=vehicle.images or [],
    )
    ove_refresh, source_platform = _enqueue_auction_detail_refresh(
        db,
        vehicle=vehicle,
        current_deal=current_deal,
        current_user=current_user,
        priority=220,
        reason=f"garage_acquisition_started:{current_deal.id}",
    )

    if ove_refresh:
        log_event(
            db,
            deal_id=current_deal.id,
            event_type="buyer_auction_detail_refresh_requested",
            actor="buyer",
            payload={
                "vin": vehicle.vin,
                "trigger": "garage_acquisition_started",
                "source_platform": source_platform.value,
                **ove_refresh,
            },
        )
    try:
        GHLLifecycleService().record_garage_acquisition_started(
            user=current_user,
            deal=current_deal,
            vin=vehicle.vin,
            started_at=item.acquisition_started_at,
        )
    except Exception:
        pass

    db.commit()
    db.refresh(item)
    return ok(
        {
            "garage_item": _serialize_garage_item(
                db,
                item,
                vehicle,
                deal_stage=current_deal.stage,
                allow_protected_photos=can_view_protected_vehicle_photos(user=current_user, deal=current_deal),
            ),
            "deal": {
                "id": current_deal.id,
                "stage": current_deal.stage.value,
                "selected_vin": current_deal.selected_vin,
            },
            "ove_detail_refresh": ove_refresh,
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
    current_user: User = Depends(get_current_user),
    current_deal=Depends(get_current_deal),
) -> dict:
    if not is_admin_user(current_user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only admins can initiate returns from My Garage")

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
        .where(Notification.is_read.is_(False))
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


@router.post("/notifications/mark-read")
def mark_notifications_read(
    payload: MarkNotificationsReadRequest | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    statement = select(Notification).where(
        Notification.user_id == current_user.id,
        Notification.is_read.is_(False),
    )
    if payload and payload.ids:
        statement = statement.where(Notification.id.in_(payload.ids))

    notifications = db.scalars(statement).all()
    for notification in notifications:
        notification.is_read = True

    db.commit()
    return ok({"marked_read": len(notifications)})
