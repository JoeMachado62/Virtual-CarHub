from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.core.constants import InventorySourceType
from app.models.entities import HotDeal, Vehicle
from app.schemas.hot_deals import HotDealIngestRequest, HotDealItemPayload
from app.schemas.ove_inventory import OveDetailPushRequest, OveImagePayload
from app.services.image_pipeline_service import resolve_vehicle_card_media
from app.services.ove_inventory_service import upsert_ove_vehicle_detail


class HotDealBatchValidationError(ValueError):
    def __init__(self, report: dict[str, Any]):
        self.report = report
        super().__init__("Hot Deals batch did not contain any valid deals")


def _now() -> datetime:
    return datetime.now(UTC)


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _platform_value(value: Any) -> str:
    return getattr(value, "value", value) or "manheim"


def _image_payloads(deal: HotDealItemPayload) -> list[OveImagePayload]:
    if deal.detail.images:
        return deal.detail.images
    return [
        OveImagePayload(url=url, role="gallery", display_order=index, is_primary=index == 0)
        for index, url in enumerate(deal.vehicle.images)
        if url
    ]


def _condition_report_for_detail(deal: HotDealItemPayload) -> dict[str, Any]:
    report = dict(deal.detail.condition_report or {})
    metadata = dict(report.get("metadata") or {})
    metadata.setdefault("announcementsEnrichment", {"announcements": []})
    report["metadata"] = metadata
    report.setdefault("announcements", [])
    report.setdefault("damage_items", [])
    report.setdefault("damage_summary", {"total_items": 0, "structural_issue": False})

    history = dict(report.get("vehicle_history") or {})
    history.setdefault("owners", 0)
    history.setdefault("accidents", 0)
    history.setdefault("engine_starts", True)
    history.setdefault("drivable", True)
    report["vehicle_history"] = history

    tire_depths = dict(report.get("tire_depths") or {})
    for key, label in (("lf", "LF"), ("rf", "RF"), ("lr", "LR"), ("rr", "RR")):
        tire_depths.setdefault(key, {"position_label": label, "tread_depth": "Not Inspected"})
    report["tire_depths"] = tire_depths
    return report


def _upsert_vehicle(db: Session, deal: HotDealItemPayload, *, source_platform: str) -> Vehicle:
    vehicle_payload = deal.vehicle
    vehicle = db.get(Vehicle, deal.vin)
    if not vehicle:
        vehicle = Vehicle(
            vin=deal.vin,
            year=vehicle_payload.year,
            make=vehicle_payload.make,
            model=vehicle_payload.model,
            price_asking=vehicle_payload.price_asking,
        )
        db.add(vehicle)

    normalized = dict(vehicle_payload.features_normalized or {})
    normalized.setdefault("mmr", deal.pricing.mmr_value)
    normalized.setdefault("manheim_mmr", deal.pricing.mmr_value)
    normalized.setdefault("hot_deal_delta", deal.pricing.deal_delta)
    normalized.setdefault("hot_deal_label", deal.pricing.deal_label)
    normalized.setdefault("auction_start_at", _as_utc(deal.auction_start_at).isoformat() if deal.auction_start_at else None)
    normalized.setdefault("auction_end_at", _as_utc(deal.auction_end_at).isoformat())
    normalized.setdefault("source_platform", source_platform)
    normalized = {k: v for k, v in normalized.items() if v is not None}

    vehicle.listing_id = deal.listing_id or vehicle.listing_id
    vehicle.year = vehicle_payload.year
    vehicle.make = vehicle_payload.make
    vehicle.model = vehicle_payload.model
    vehicle.trim = vehicle_payload.trim
    vehicle.body_type = vehicle_payload.body_type
    vehicle.sub_body_type = vehicle_payload.sub_body_type
    vehicle.engine_type = vehicle_payload.engine_type
    vehicle.cylinders = vehicle_payload.cylinders
    vehicle.forced_induction = vehicle_payload.forced_induction
    vehicle.drivetrain = vehicle_payload.drivetrain
    vehicle.mpg_combined = vehicle_payload.mpg_combined
    vehicle.ev_range = vehicle_payload.ev_range
    vehicle.towing_capacity_lbs = vehicle_payload.towing_capacity_lbs
    vehicle.odometer = vehicle_payload.odometer
    vehicle.condition_grade = vehicle_payload.condition_grade
    vehicle.price_asking = vehicle_payload.price_asking
    vehicle.price_wholesale_est = vehicle_payload.price_wholesale_est
    vehicle.location_zip = vehicle_payload.location_zip
    vehicle.location_state = vehicle_payload.location_state
    vehicle.source_type = InventorySourceType.OVE.value
    vehicle.source_url = deal.listing_url or vehicle_payload.source_url
    vehicle.images = vehicle_payload.images or vehicle.images
    vehicle.features_raw = vehicle_payload.features_raw or vehicle.features_raw
    vehicle.features_normalized = normalized
    vehicle.available = True
    vehicle.quality_firewall_pass = True
    vehicle.last_seen_active = _now()
    return vehicle


def _upsert_detail(db: Session, deal: HotDealItemPayload, *, source_platform: str, batch: HotDealIngestRequest) -> None:
    snapshot = deal.detail.listing_snapshot
    if not snapshot.page_url:
        snapshot.page_url = deal.listing_url or deal.vehicle.source_url

    sync_metadata = dict(deal.detail.sync_metadata or {})
    sync_metadata.update(
        {
            "hot_deal": True,
            "batch_id": batch.batch_id,
            "source_list_name": batch.source_list_name,
            "scraped_at": batch.scraped_at.isoformat() if batch.scraped_at else None,
        }
    )
    payload = OveDetailPushRequest(
        source_platform=source_platform,
        images=_image_payloads(deal),
        condition_report=_condition_report_for_detail(deal),
        seller_comments=deal.detail.seller_comments,
        listing_snapshot=snapshot,
        sync_metadata={k: v for k, v in sync_metadata.items() if v is not None},
    )
    upsert_ove_vehicle_detail(db, vin=deal.vin, payload=payload)


def _hot_deal_payload(batch: HotDealIngestRequest, deal: HotDealItemPayload) -> dict[str, Any]:
    return {
        "batch": batch.model_dump(mode="json", exclude={"deals"}),
        "deal": deal.model_dump(mode="json"),
    }


def _compact_validation_errors(exc: ValidationError, *, limit: int = 6) -> list[dict[str, str]]:
    compact: list[dict[str, str]] = []
    for error in exc.errors(include_input=False)[:limit]:
        loc = ".".join(str(part) for part in error.get("loc", ()))
        compact.append(
            {
                "field": loc or "payload",
                "message": str(error.get("msg", "Invalid value")),
                "type": str(error.get("type", "value_error")),
            }
        )
    return compact


def _raw_batch_metadata(raw: dict[str, Any], deals: list[HotDealItemPayload]) -> HotDealIngestRequest:
    return HotDealIngestRequest.model_validate({**raw, "deals": deals})


def validate_hot_deals_batch(raw: dict[str, Any]) -> tuple[HotDealIngestRequest, list[dict[str, Any]], int]:
    raw_deals = raw.get("deals") or []
    if not isinstance(raw_deals, list):
        raise HotDealBatchValidationError(
            {
                "requested": 0,
                "accepted": 0,
                "rejected": 0,
                "batch_errors": [{"field": "deals", "message": "Input should be a list", "type": "list_type"}],
            }
        )

    valid_deals: list[HotDealItemPayload] = []
    rejected_items: list[dict[str, Any]] = []
    for index, raw_deal in enumerate(raw_deals):
        vin = raw_deal.get("vin") if isinstance(raw_deal, dict) else None
        try:
            deal = HotDealItemPayload.model_validate(raw_deal)
            source_platform = _platform_value(deal.source_platform or raw.get("source_platform"))
            OveDetailPushRequest(
                source_platform=source_platform,
                images=_image_payloads(deal),
                condition_report=_condition_report_for_detail(deal),
                seller_comments=deal.detail.seller_comments,
                listing_snapshot=deal.detail.listing_snapshot,
                sync_metadata=deal.detail.sync_metadata,
            )
            valid_deals.append(deal)
        except ValidationError as exc:
            rejected_items.append(
                {
                    "index": index,
                    "vin": str(vin).strip().upper() if vin else None,
                    "errors": _compact_validation_errors(exc),
                }
            )

    try:
        payload = _raw_batch_metadata(raw, valid_deals)
    except ValidationError as exc:
        raise HotDealBatchValidationError(
            {
                "requested": len(raw_deals),
                "accepted": len(valid_deals),
                "rejected": len(rejected_items),
                "rejected_items": rejected_items[:50],
                "batch_errors": _compact_validation_errors(exc),
            }
        ) from exc

    return payload, rejected_items, len(raw_deals)


def ingest_hot_deals_resilient(db: Session, raw: dict[str, Any]) -> dict[str, Any]:
    payload, rejected_items, requested = validate_hot_deals_batch(raw)

    if not payload.deals:
        report = {
            "source_list_name": payload.source_list_name,
            "batch_id": payload.batch_id,
            "snapshot_mode": payload.snapshot_mode,
            "requested": requested,
            "accepted": 0,
            "upserted_vehicles": 0,
            "upserted_details": 0,
            "hot_deals_inserted": 0,
            "hot_deals_updated": 0,
            "hot_deals_deactivated": 0,
            "rejected": len(rejected_items),
            "active_count": db.scalar(
                select(func.count()).select_from(HotDeal).where(
                    HotDeal.is_active.is_(True),
                    HotDeal.expires_at > _now(),
                )
            )
            or 0,
            "rejected_items": rejected_items[:50],
        }
        raise HotDealBatchValidationError(report)

    report = ingest_hot_deals(db, payload)
    report.update(
        {
            "requested": requested,
            "accepted": len(payload.deals),
            "upserted_vehicles": len(payload.deals),
            "rejected": len(rejected_items),
            "rejected_items": rejected_items[:50],
        }
    )
    return report


def ingest_hot_deals(db: Session, payload: HotDealIngestRequest) -> dict[str, Any]:
    now = _now()
    requested = len(payload.deals)
    inserted = 0
    updated = 0
    upserted_details = 0
    rejected = 0
    active_vins: set[str] = set()

    for deal in payload.deals:
        source_platform = _platform_value(deal.source_platform or payload.source_platform)
        vehicle = _upsert_vehicle(db, deal, source_platform=source_platform)
        db.flush()

        _upsert_detail(db, deal, source_platform=source_platform, batch=payload)
        upserted_details += 1

        active_vins.add(deal.vin)
        existing = db.scalar(
            select(HotDeal)
            .where(
                HotDeal.vin == deal.vin,
                HotDeal.is_active.is_(True),
            )
            .order_by(HotDeal.updated_at.desc())
            .limit(1)
        )
        hot_deal = existing or HotDeal(vin=deal.vin)
        if existing:
            updated += 1
        else:
            inserted += 1
            db.add(hot_deal)

        auction_end_at = _as_utc(deal.auction_end_at)
        featured_until = _as_utc(deal.marketing.featured_until)
        hot_deal.source_platform = source_platform
        hot_deal.source_list_name = payload.source_list_name
        hot_deal.batch_id = payload.batch_id
        hot_deal.snapshot_mode = payload.snapshot_mode
        hot_deal.listing_id = deal.listing_id
        hot_deal.listing_url = deal.listing_url or vehicle.source_url
        hot_deal.auction_start_at = _as_utc(deal.auction_start_at)
        hot_deal.auction_end_at = auction_end_at
        hot_deal.mmr_value = deal.pricing.mmr_value
        hot_deal.asking_price = deal.pricing.asking_price
        hot_deal.deal_delta = deal.pricing.deal_delta
        hot_deal.deal_delta_pct = deal.pricing.deal_delta_pct
        hot_deal.deal_label = deal.pricing.deal_label
        hot_deal.deal_rank = deal.pricing.deal_rank
        hot_deal.cr_screen_status = deal.cr_screen.status.lower()
        hot_deal.cr_screen_reasons = deal.cr_screen.reasons
        hot_deal.marketing_title = deal.marketing.title
        hot_deal.marketing_summary = deal.marketing.summary
        hot_deal.hero_image_url = (deal.vehicle.images or [None])[0]
        hot_deal.is_active = auction_end_at > now and hot_deal.cr_screen_status == "passed"
        hot_deal.featured_until = featured_until
        hot_deal.expires_at = auction_end_at
        hot_deal.payload_json = _hot_deal_payload(payload, deal)

    deactivated = 0
    if payload.snapshot_mode == "full_replace":
        stmt = select(HotDeal).where(
            HotDeal.is_active.is_(True),
            HotDeal.source_list_name == payload.source_list_name,
        )
        if active_vins:
            stmt = stmt.where(HotDeal.vin.not_in(active_vins))
        for stale in db.scalars(stmt).all():
            stale.is_active = False
            deactivated += 1

    expired = db.scalars(
        select(HotDeal).where(
            and_(
                HotDeal.is_active.is_(True),
                HotDeal.expires_at <= now,
            )
        )
    ).all()
    for row in expired:
        row.is_active = False
    deactivated += len(expired)

    db.flush()
    active_count = db.scalar(
        select(func.count()).select_from(HotDeal).where(
            HotDeal.is_active.is_(True),
            HotDeal.expires_at > now,
        )
    ) or 0

    return {
        "source_list_name": payload.source_list_name,
        "batch_id": payload.batch_id,
        "snapshot_mode": payload.snapshot_mode,
        "requested": requested,
        "upserted_vehicles": requested - rejected,
        "upserted_details": upserted_details,
        "hot_deals_inserted": inserted,
        "hot_deals_updated": updated,
        "hot_deals_deactivated": deactivated,
        "rejected": rejected,
        "active_count": active_count,
    }


def serialize_hot_deal(row: HotDeal, *, db: Session | None = None) -> dict[str, Any]:
    vehicle = row.vehicle
    public_media = None
    if db is not None and vehicle is not None:
        public_media = resolve_vehicle_card_media(
            db,
            vehicle=vehicle,
            allow_protected_photos=False,
        )
    return {
        "id": row.id,
        "vin": row.vin,
        "public_slug": vehicle.public_slug if vehicle else None,
        "year": vehicle.year if vehicle else None,
        "make": vehicle.make if vehicle else None,
        "model": vehicle.model if vehicle else None,
        "trim": vehicle.trim if vehicle else None,
        "price_asking": row.asking_price,
        "location_state": vehicle.location_state if vehicle else None,
        "location_zip": vehicle.location_zip if vehicle else None,
        "source_label": "Hot Deal",
        "source_type": vehicle.source_type if vehicle else InventorySourceType.OVE.value,
        "thumbnail": public_media.thumbnail if public_media else None,
        "image_display_mode": public_media.display_mode.value if public_media else None,
        "inspection_status": public_media.inspection_status.value if public_media else None,
        "has_inspection_report": public_media.has_inspection_report if public_media else False,
        "dealer_photos_gated": public_media.dealer_photos_gated if public_media else False,
        "gated_photo_count": public_media.gated_photo_count if public_media else 0,
        "reference_pending": public_media.reference_pending if public_media else False,
        "mmr_value": row.mmr_value,
        "deal_delta": row.deal_delta,
        "deal_delta_pct": row.deal_delta_pct,
        "deal_label": row.deal_label,
        "deal_rank": row.deal_rank,
        "auction_start_at": row.auction_start_at.isoformat() if row.auction_start_at else None,
        "auction_end_at": row.auction_end_at.isoformat(),
        "expires_at": row.expires_at.isoformat(),
        "featured_until": row.featured_until.isoformat() if row.featured_until else None,
        "marketing_title": row.marketing_title,
        "marketing_summary": row.marketing_summary,
        "is_active": row.is_active,
        "vdp_path": f"/vinventory/{vehicle.public_slug or row.vin}" if vehicle else f"/vinventory/{row.vin}",
    }


def get_active_hot_deals(db: Session, *, limit: int = 12) -> list[dict[str, Any]]:
    now = _now()
    rows = db.scalars(
        select(HotDeal)
        .join(HotDeal.vehicle)
        .where(
            HotDeal.is_active.is_(True),
            HotDeal.expires_at > now,
            HotDeal.cr_screen_status == "passed",
        )
        .order_by(HotDeal.deal_rank.asc(), HotDeal.deal_delta.desc(), HotDeal.expires_at.asc())
        .limit(limit)
    ).all()
    return [serialize_hot_deal(row, db=db) for row in rows]
