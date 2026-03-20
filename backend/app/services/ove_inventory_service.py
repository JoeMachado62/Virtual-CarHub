from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.constants import AuctionPlatform, InventorySourceType, OveDetailRequestStatus
from app.models.entities import OveDetailRequest, OveVehicleDetail, Vehicle
from app.schemas.ove_inventory import (
    OveBulkIngestRequest,
    OveDetailPushRequest,
    OveDetailRequestEnqueueRequest,
)
from app.services.imagin_service import sync_imagin_source_assets
from app.services.image_pipeline_service import ensure_tier2_hero_job, sync_source_assets
from app.services.inventory_service import upsert_vehicle_with_source_priority


@dataclass(slots=True)
class OveBulkIngestReport:
    source: str = InventorySourceType.OVE.value
    requested: int = 0
    inserted: int = 0
    updated: int = 0
    skipped_priority: int = 0
    skipped_invalid: int = 0
    marked_sold: int = 0
    synced_vins: list[str] = field(default_factory=list)
    source_platforms: list[str] = field(default_factory=list)
    sync_metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def ingest_ove_inventory(db: Session, payload: OveBulkIngestRequest) -> OveBulkIngestReport:
    report = OveBulkIngestReport(
        requested=len(payload.vehicles),
        sync_metadata=payload.sync_metadata,
    )
    now = datetime.now(UTC)
    full_snapshot = payload.sync_metadata.get("full_snapshot")
    if full_snapshot is None:
        full_snapshot = str(payload.sync_metadata.get("snapshot_mode", "full")).strip().lower() != "partial"
    current_batch_vins: set[str] = set()

    for item in payload.vehicles:
        incoming = item.model_dump()
        source_platform = item.source_platform.value
        source_type = incoming.pop("source_type").value
        incoming.pop("source_platform", None)
        normalized_features = dict(incoming.get("features_normalized") or {})
        normalized_features["source_platform"] = source_platform
        incoming["features_normalized"] = normalized_features
        incoming["last_seen_active"] = now
        incoming["source_type"] = source_type
        current_batch_vins.add(item.vin)

        existing = db.get(Vehicle, item.vin)
        action = upsert_vehicle_with_source_priority(
            existing=existing,
            incoming=incoming,
            incoming_source=source_type,
        )
        vehicle_row = existing
        if action == "inserted":
            vehicle_row = Vehicle(**incoming)
            db.add(vehicle_row)
            report.inserted += 1
        elif action == "updated":
            vehicle_row = existing
            report.updated += 1
        else:
            vehicle_row = existing
            report.skipped_priority += 1

        if item.vin not in report.synced_vins:
            report.synced_vins.append(item.vin)
        if source_platform not in report.source_platforms:
            report.source_platforms.append(source_platform)

        sync_source_assets(
            db,
            vin=item.vin,
            listing_id=item.listing_id,
            image_urls=item.images,
            source_kind=source_type,
            source_platform=item.source_platform,
        )
        if vehicle_row is not None:
            sync_imagin_source_assets(
                db,
                vehicle=vehicle_row,
                listing_id=item.listing_id,
                source_platform=item.source_platform,
            )
        ensure_tier2_hero_job(
            db,
            vin=item.vin,
            trigger_event="ove_ingest",
            primary_image_url=item.images[0] if item.images else None,
        )

    # Only mark vehicles as unavailable if this is a complete snapshot
    # For multi-batch imports, we need to wait until all batches are complete
    batch_number = payload.sync_metadata.get("batch_number")
    batch_total = payload.sync_metadata.get("batch_total")
    is_final_batch = (batch_number == batch_total) if (batch_number and batch_total) else True

    if full_snapshot and current_batch_vins and is_final_batch:
        # For multi-batch imports, we'd need to collect all VINs from all batches
        # For now, only do this for single-batch full snapshots
        if not batch_total or batch_total == 1:
            report.marked_sold = _mark_missing_ove_inventory_unavailable(
                db,
                present_vins=current_batch_vins,
                source_platforms=report.source_platforms,
                now=now,
            )

    db.flush()
    return report


def _mark_missing_ove_inventory_unavailable(
    db: Session,
    *,
    present_vins: set[str],
    source_platforms: list[str],
    now: datetime,
) -> int:
    if not present_vins:
        return 0

    platform_expr = func.lower(func.coalesce(Vehicle.features_normalized["source_platform"].as_string(), ""))
    stmt = select(Vehicle).where(
        func.lower(Vehicle.source_type) == InventorySourceType.OVE.value,
        Vehicle.available.is_(True),
        ~Vehicle.vin.in_(sorted(present_vins)),
    )

    normalized_platforms = {str(value).strip().lower() for value in source_platforms if str(value).strip()}
    if normalized_platforms:
        platform_filters = [platform_expr.in_(sorted(normalized_platforms))]
        if AuctionPlatform.MANHEIM.value in normalized_platforms:
            # Legacy rows were ingested before source_platform was stamped into features_normalized.
            platform_filters.append(platform_expr == "")
        stmt = stmt.where(or_(*platform_filters))

    stale_rows = db.scalars(stmt).all()
    for row in stale_rows:
        row.available = False
        row.last_seen_active = now
        normalized = dict(row.features_normalized or {})
        normalized["status"] = "Sold"
        row.features_normalized = normalized

    return len(stale_rows)


def enqueue_ove_detail_request(
    db: Session,
    *,
    vin: str,
    payload: OveDetailRequestEnqueueRequest,
) -> tuple[OveDetailRequest, bool]:
    normalized_vin = vin.strip().upper()
    existing = db.scalar(
        select(OveDetailRequest)
        .where(
            OveDetailRequest.vin == normalized_vin,
            OveDetailRequest.status.in_(
                [
                    OveDetailRequestStatus.PENDING,
                    OveDetailRequestStatus.IN_PROGRESS,
                ]
            ),
        )
        .order_by(OveDetailRequest.priority.desc(), OveDetailRequest.requested_at.asc())
        .limit(1)
    )
    if existing:
        return existing, True

    request = OveDetailRequest(
        vin=normalized_vin,
        source_platform=payload.source_platform,
        status=OveDetailRequestStatus.PENDING,
        priority=payload.priority,
        request_source=payload.request_source,
        requested_by=payload.requested_by,
        reason=payload.reason,
        metadata_json=payload.metadata,
        requested_at=datetime.now(UTC),
    )
    db.add(request)
    db.flush()
    return request, False


def get_pending_ove_detail_requests(db: Session, *, limit: int = 50) -> list[OveDetailRequest]:
    stmt = (
        select(OveDetailRequest)
        .where(OveDetailRequest.status == OveDetailRequestStatus.PENDING)
        .order_by(
            OveDetailRequest.priority.desc(),
            OveDetailRequest.requested_at.asc(),
            OveDetailRequest.created_at.asc(),
        )
        .limit(limit)
    )
    return db.scalars(stmt).all()


def upsert_ove_vehicle_detail(
    db: Session,
    *,
    vin: str,
    payload: OveDetailPushRequest,
) -> tuple[OveVehicleDetail, list[OveDetailRequest], bool]:
    normalized_vin = vin.strip().upper()
    vehicle = db.get(Vehicle, normalized_vin)
    if not vehicle:
        raise LookupError("Vehicle not found")

    detail = db.get(OveVehicleDetail, normalized_vin)
    if not detail:
        detail = OveVehicleDetail(vin=normalized_vin, source_platform=payload.source_platform)
        db.add(detail)

    image_urls = [row.url.strip() for row in payload.images if row.url.strip()]
    vehicle.images = image_urls or vehicle.images
    vehicle.source_type = InventorySourceType.OVE.value
    if payload.listing_snapshot.page_url:
        vehicle.source_url = payload.listing_snapshot.page_url

    detail.source_platform = payload.source_platform
    detail.seller_comments = payload.seller_comments
    detail.images_json = [row.model_dump() for row in payload.images]
    detail.condition_report_json = payload.condition_report
    detail.listing_snapshot_json = payload.listing_snapshot.model_dump()
    detail.sync_metadata_json = payload.sync_metadata
    detail.raw_payload_json = payload.model_dump()
    detail.page_url = payload.listing_snapshot.page_url
    detail.last_synced_at = datetime.now(UTC)

    sync_source_assets(
        db,
        vin=normalized_vin,
        listing_id=vehicle.listing_id,
        image_urls=image_urls,
        source_kind=InventorySourceType.OVE.value,
        source_platform=payload.source_platform,
    )
    sync_imagin_source_assets(
        db,
        vehicle=vehicle,
        listing_id=vehicle.listing_id,
        source_platform=payload.source_platform,
    )
    hero_job = ensure_tier2_hero_job(
        db,
        vin=normalized_vin,
        trigger_event="ove_detail_push",
        primary_image_url=image_urls[0] if image_urls else None,
    )

    completed_requests = db.scalars(
        select(OveDetailRequest)
        .where(
            OveDetailRequest.vin == normalized_vin,
            OveDetailRequest.status.in_(
                [
                    OveDetailRequestStatus.PENDING,
                    OveDetailRequestStatus.IN_PROGRESS,
                ]
            ),
        )
        .order_by(OveDetailRequest.requested_at.asc())
    ).all()
    now = datetime.now(UTC)
    for request in completed_requests:
        request.status = OveDetailRequestStatus.COMPLETED
        request.fulfilled_at = now
        request.detail_received_at = now

    db.flush()
    return detail, completed_requests, hero_job is not None


def serialize_request_timestamp(value: datetime | None) -> str | None:
    if value is None:
        return None
    normalized = value if value.tzinfo else value.replace(tzinfo=UTC)
    return normalized.astimezone(UTC).isoformat()
