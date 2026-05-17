from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import and_, case, cast, delete, func, or_, select, update
from sqlalchemy.dialects.postgresql import JSONB as PG_JSONB
from sqlalchemy.types import JSON as SA_JSON
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.constants import AuctionPlatform, InventorySourceType, OveDetailRequestStatus
from app.models.entities import OveDetailRequest, OveScraperHeartbeat, OveVehicleDetail, Vehicle
from app.schemas.ove_inventory import (
    OveBulkIngestRequest,
    OveDetailPushRequest,
    OveDetailRequestEnqueueRequest,
    OveImagePayload,
)
from app.services.chromedata_service import build_chromedata_manifest, sync_chromedata_source_assets
from app.services.image_pipeline_service import canonical_source_image_url, ensure_tier2_hero_job, sync_source_assets
from app.services.zip_radius_service import normalize_zip_code


# Statuses that represent active in-flight work that should not be re-claimed
# while still owned by another worker.
_ACTIVE_REQUEST_STATUSES = (
    OveDetailRequestStatus.PENDING,
    OveDetailRequestStatus.CLAIMED,
    OveDetailRequestStatus.IN_PROGRESS,
)

# Terminal statuses that should never be re-served by the queue.
_TERMINAL_REQUEST_STATUSES = (
    OveDetailRequestStatus.COMPLETED,
    OveDetailRequestStatus.CANCELED,
    OveDetailRequestStatus.TERMINAL,
)


class OveDetailRequestNotFoundError(LookupError):
    """Raised when a request_id does not exist."""


class OveDetailRequestOwnershipError(PermissionError):
    """Raised when a worker tries to mutate a request it does not own."""


class OveDetailRequestStateError(ValueError):
    """Raised when a request is in a state incompatible with the requested op."""

logger = logging.getLogger(__name__)


class OveSnapshotRejectedError(ValueError):
    """Raised when a full-snapshot ingest fails sanity checks before any
    destructive operation runs. The request should be rejected entirely so
    the prior good snapshot remains untouched."""


@dataclass(slots=True)
class OveBulkIngestReport:
    source: str = InventorySourceType.OVE.value
    requested: int = 0
    inserted: int = 0
    updated: int = 0
    skipped_priority: int = 0
    skipped_invalid: int = 0
    skipped_quality: int = 0
    unavailable_missing_zip: int = 0
    marked_sold: int = 0
    synced_vins: list[str] = field(default_factory=list)
    source_platforms: list[str] = field(default_factory=list)
    sync_metadata: dict[str, Any] = field(default_factory=dict)
    snapshot_replaced: bool = False
    snapshot_skipped_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


_VEHICLE_UPSERT_COLUMNS = (
    "listing_id", "year", "make", "model", "trim", "body_type", "sub_body_type",
    "engine_type", "cylinders", "forced_induction", "drivetrain", "mpg_combined",
    "ev_range", "towing_capacity_lbs", "odometer", "condition_grade",
    "price_asking", "price_wholesale_est", "location_zip", "location_state",
    "source_type", "source_url", "images",
    "available", "quality_firewall_pass", "last_seen_active",
)

# Columns that contain enrichment data (e.g. from MarketCheck) and should
# not be blindly overwritten when a VIN already exists in the DB.
_ENRICHMENT_PRESERVED_COLUMNS = ("features_raw", "features_normalized")


def _build_vehicle_row(item, now: datetime) -> dict[str, Any]:
    """Transform an OveVehicleIngestItem into a flat dict for Vehicle upsert."""
    source_platform = item.source_platform.value
    source_type = item.source_type.value
    location_zip = normalize_zip_code(item.location_zip)
    has_location_zip = location_zip is not None

    # Build features_normalized with display fields for frontend consistency
    normalized_features = dict(item.features_normalized or {})
    normalized_features["source_platform"] = source_platform
    if not has_location_zip:
        normalized_features["status"] = "Unavailable"
        normalized_features["unavailable_reason"] = "missing_location_zip"
        normalized_features["missing_location_zip_at"] = now.isoformat()

    display_map = {
        "exterior_color": "exterior_color",
        "interior_color": "interior_color",
        "transmission_type": "transmission",
        "fuel_type": "fuel_type",
        "odometer_units": "odometer_units",
        "pickup_location": "pickup_location",
    }
    for item_field, norm_key in display_map.items():
        val = getattr(item, item_field, None)
        if val:
            normalized_features.setdefault(norm_key, val)

    if item.engine_type:
        normalized_features.setdefault("engine_type", item.engine_type)
    if item.drivetrain:
        normalized_features.setdefault("drivetrain", item.drivetrain)
    if item.body_type:
        normalized_features.setdefault("body_type", item.body_type)
    if item.condition_grade:
        normalized_features.setdefault("condition_report_grade", item.condition_grade)
    if not normalized_features.get("auction_house") and source_platform:
        normalized_features["auction_house"] = source_platform.replace("_", " ").title()

    return {
        "vin": item.vin,
        "listing_id": item.listing_id,
        "year": item.year,
        "make": item.make,
        "model": item.model,
        "trim": item.trim,
        "body_type": item.body_type,
        "sub_body_type": item.sub_body_type,
        "engine_type": item.engine_type,
        "cylinders": item.cylinders,
        "forced_induction": item.forced_induction,
        "drivetrain": item.drivetrain,
        "mpg_combined": item.mpg_combined,
        "ev_range": item.ev_range,
        "towing_capacity_lbs": item.towing_capacity_lbs,
        "odometer": item.odometer,
        "condition_grade": item.condition_grade,
        "price_asking": item.price_asking,
        "price_wholesale_est": item.price_wholesale_est,
        "location_zip": location_zip,
        "location_state": item.location_state,
        "source_type": source_type,
        "source_url": item.source_url,
        "images": item.images,
        "features_raw": item.features_raw,
        "features_normalized": normalized_features,
        "available": has_location_zip,
        "quality_firewall_pass": item.quality_firewall_pass,
        "last_seen_active": now,
    }


def _bulk_upsert_vehicles_pg(db: Session, rows: list[dict[str, Any]]) -> None:
    """PostgreSQL bulk upsert using INSERT ... ON CONFLICT DO UPDATE.

    Enrichment-sensitive columns (features_raw, features_normalized) are
    merged so that data added by MarketCheck or other enrichment sources
    is preserved when a VIN already exists.  Strategy:
      - features_normalized: incoming keys as base, existing keys overlay
        (existing enrichment wins over scraper defaults).
      - features_raw: keep existing if non-empty, otherwise use incoming.
    """
    CHUNK_SIZE = 2000
    for i in range(0, len(rows), CHUNK_SIZE):
        chunk = rows[i : i + CHUNK_SIZE]
        stmt = pg_insert(Vehicle).values(chunk)

        set_clause = {col: stmt.excluded[col] for col in _VEHICLE_UPSERT_COLUMNS}

        # features_normalized: merge incoming under existing so enrichment
        # keys added after initial ingest are preserved.
        # Cast json → jsonb for the || merge, then back to json.
        # The || operator gives right-side keys priority, so we put existing
        # on the right to preserve enrichment over scraper defaults.
        set_clause["features_normalized"] = cast(
            func.coalesce(
                cast(stmt.excluded["features_normalized"], PG_JSONB),
                cast(func.cast("{}", SA_JSON), PG_JSONB),
            ).op("||")(
                func.coalesce(
                    cast(Vehicle.features_normalized, PG_JSONB),
                    cast(func.cast("{}", SA_JSON), PG_JSONB),
                )
            ),
            SA_JSON,
        )

        # features_raw: keep existing if it has content, otherwise use incoming.
        set_clause["features_raw"] = case(
            (
                and_(
                    Vehicle.features_raw.isnot(None),
                    func.json_typeof(Vehicle.features_raw) == "array",
                    func.json_array_length(Vehicle.features_raw) > 0,
                ),
                Vehicle.features_raw,
            ),
            else_=stmt.excluded["features_raw"],
        )

        stmt = stmt.on_conflict_do_update(
            index_elements=["vin"],
            set_=set_clause,
        )
        db.execute(stmt)


def _apply_missing_zip_availability_metadata(db: Session, rows: list[dict[str, Any]], now: datetime) -> None:
    valid_vins = [row["vin"] for row in rows if row["available"]]
    missing_zip_vins = [row["vin"] for row in rows if not row["available"]]

    if valid_vins:
        features_without_missing_zip_flags = cast(
            cast(Vehicle.features_normalized, PG_JSONB)
            .op("-")("unavailable_reason")
            .op("-")("missing_location_zip_at"),
            PG_JSONB,
        )
        cleaned_features = case(
            (
                Vehicle.features_normalized["status"].as_string() == "Unavailable",
                features_without_missing_zip_flags.op("-")("status"),
            ),
            else_=features_without_missing_zip_flags,
        )
        db.execute(
            update(Vehicle)
            .where(Vehicle.vin.in_(valid_vins))
            .values(features_normalized=cast(cleaned_features, SA_JSON))
        )

    if missing_zip_vins:
        unavailable_metadata = func.jsonb_build_object(
            "status",
            "Unavailable",
            "unavailable_reason",
            "missing_location_zip",
            "missing_location_zip_at",
            now.isoformat(),
        )
        db.execute(
            update(Vehicle)
            .where(Vehicle.vin.in_(missing_zip_vins))
            .values(
                available=False,
                features_normalized=cast(
                    func.coalesce(
                        cast(Vehicle.features_normalized, PG_JSONB),
                        cast(func.cast("{}", SA_JSON), PG_JSONB),
                    ).op("||")(unavailable_metadata),
                    SA_JSON,
                ),
            )
        )


def deactivate_missing_zip_ove_inventory(
    db: Session,
    *,
    max_mark: int = 5000,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Mark active OVE rows unavailable when they cannot be geographically placed."""
    now = datetime.now(UTC)
    missing_zip_filter = [
        func.lower(Vehicle.source_type) == InventorySourceType.OVE.value,
        Vehicle.available.is_(True),
        or_(
            Vehicle.location_zip.is_(None),
            func.length(func.trim(func.coalesce(Vehicle.location_zip, ""))) < 5,
        ),
    ]

    total_missing = db.scalar(
        select(func.count()).select_from(Vehicle).where(*missing_zip_filter)
    ) or 0

    if dry_run or total_missing == 0:
        return {
            "dry_run": dry_run,
            "total_missing_zip_found": total_missing,
            "marked_unavailable": 0,
            "capped": False,
            "remaining_missing_zip": total_missing if dry_run else 0,
        }

    vins = [
        row[0]
        for row in db.execute(
            select(Vehicle.vin)
            .where(*missing_zip_filter)
            .order_by(Vehicle.updated_at.asc())
            .limit(max_mark)
        ).all()
    ]

    if not vins:
        return {
            "dry_run": False,
            "total_missing_zip_found": total_missing,
            "marked_unavailable": 0,
            "capped": False,
            "remaining_missing_zip": 0,
        }

    unavailable_metadata = func.jsonb_build_object(
        "status",
        "Unavailable",
        "unavailable_reason",
        "missing_location_zip",
        "missing_location_zip_at",
        now.isoformat(),
    )
    marked = db.execute(
        update(Vehicle)
        .where(Vehicle.vin.in_(vins))
        .values(
            available=False,
            updated_at=now,
            features_normalized=cast(
                func.coalesce(
                    cast(Vehicle.features_normalized, PG_JSONB),
                    cast(func.cast("{}", SA_JSON), PG_JSONB),
                ).op("||")(unavailable_metadata),
                SA_JSON,
            ),
        )
    ).rowcount or 0

    return {
        "dry_run": False,
        "total_missing_zip_found": total_missing,
        "marked_unavailable": marked,
        "capped": total_missing > max_mark,
        "remaining_missing_zip": max(0, total_missing - marked),
    }


def ingest_ove_inventory(
    db: Session,
    payload: OveBulkIngestRequest,
    *,
    min_count_override: int | None = None,
    min_ratio_override: float | None = None,
) -> OveBulkIngestReport:
    """Bulk-replace OVE inventory in two SQL statements.

    The scraper handles quality control and deduplication. We simply:
    1. Count existing available OVE rows.
    2. If incoming count >= 80% of existing → full replace (mark old unavailable).
    3. Bulk upsert all incoming vehicles via INSERT ... ON CONFLICT DO UPDATE.
    """
    from app.core.config import settings

    now = datetime.now(UTC)
    report = OveBulkIngestReport(
        requested=len(payload.vehicles),
        sync_metadata=payload.sync_metadata or {},
    )

    if not payload.vehicles:
        return report

    min_count = min_count_override if min_count_override is not None else int(settings.ove_snapshot_min_count or 0)
    min_ratio = min_ratio_override if min_ratio_override is not None else float(settings.ove_snapshot_min_ratio or 0.8)

    # ---- Step 1: count existing available OVE vehicles ----
    existing_available = db.scalar(
        select(func.count()).select_from(Vehicle).where(
            func.lower(Vehicle.source_type) == InventorySourceType.OVE.value,
            Vehicle.available.is_(True),
        )
    ) or 0

    # Safety guards only apply when there's already meaningful inventory.
    # First-ever ingest (existing_available == 0) always passes.
    if existing_available > 0:
        if len(payload.vehicles) < min_count:
            raise OveSnapshotRejectedError(
                f"Snapshot rejected: {len(payload.vehicles)} VINs is below "
                f"minimum threshold of {min_count}."
            )

        ratio = len(payload.vehicles) / existing_available
        if ratio < min_ratio:
            raise OveSnapshotRejectedError(
                f"Snapshot rejected: {len(payload.vehicles)} incoming vs "
                f"{existing_available} existing (ratio {ratio:.1%}) is below "
                f"{min_ratio:.0%} threshold. Looks like a truncated upload."
            )

    # ---- Step 2: mark ALL old OVE inventory unavailable ----
    marked_unavailable = db.execute(
        update(Vehicle)
        .where(
            func.lower(Vehicle.source_type) == InventorySourceType.OVE.value,
            Vehicle.available.is_(True),
        )
        .values(available=False, last_seen_active=now)
    ).rowcount
    report.marked_sold = marked_unavailable
    report.snapshot_replaced = True
    logger.info(
        "Marked %d existing OVE vehicles unavailable before bulk upsert.",
        marked_unavailable,
    )

    # ---- Step 3: bulk upsert all incoming vehicles ----
    rows = [_build_vehicle_row(item, now) for item in payload.vehicles]
    source_platforms: set[str] = set()
    for item in payload.vehicles:
        source_platforms.add(item.source_platform.value)
    missing_zip_count = sum(1 for row in rows if not row["available"])

    dialect = db.bind.dialect.name if db.bind is not None else ""
    if dialect != "postgresql":
        raise RuntimeError(f"OVE inventory ingest requires PostgreSQL, got {dialect or 'unknown'}")
    _bulk_upsert_vehicles_pg(db, rows)
    _apply_missing_zip_availability_metadata(db, rows, now)

    report.inserted = len(rows)
    report.unavailable_missing_zip = missing_zip_count
    report.synced_vins = [r["vin"] for r in rows]
    report.source_platforms = sorted(source_platforms)

    db.flush()
    logger.info(
        "OVE bulk ingest complete: %d vehicles upserted, %d missing zip left unavailable, %d old marked unavailable.",
        len(rows),
        missing_zip_count,
        marked_unavailable,
    )
    return report


def cleanup_stale_ove_inventory(
    db: Session,
    *,
    stale_threshold_days: int = 5,
    max_mark: int = 5000,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Mark OVE vehicles as unavailable if last_seen_active exceeds the staleness threshold.

    Safety guards:
    - max_mark caps the number of vehicles marked per call
    - dry_run mode for previewing impact without changes
    - Only affects source_type='ove' vehicles
    """
    cutoff = datetime.now(UTC) - timedelta(days=stale_threshold_days)
    now = datetime.now(UTC)

    stale_filter = [
        func.lower(Vehicle.source_type) == InventorySourceType.OVE.value,
        Vehicle.available.is_(True),
        Vehicle.last_seen_active < cutoff,
    ]

    total_stale = db.scalar(
        select(func.count()).select_from(Vehicle).where(*stale_filter)
    ) or 0

    if dry_run or total_stale == 0:
        return {
            "dry_run": dry_run,
            "stale_threshold_days": stale_threshold_days,
            "cutoff": cutoff.isoformat(),
            "total_stale_found": total_stale,
            "marked_unavailable": 0,
            "capped": False,
            "remaining_stale": total_stale if dry_run else 0,
        }

    rows = db.scalars(
        select(Vehicle)
        .where(*stale_filter)
        .order_by(Vehicle.last_seen_active.asc())
        .limit(max_mark)
    ).all()

    from app.services.ghl_lifecycle_service import handle_vehicle_sold

    notified_total = 0
    for row in rows:
        row.available = False
        normalized = dict(row.features_normalized or {})
        normalized["status"] = "Sold"
        normalized["cleanup_reason"] = "stale_threshold"
        normalized["cleanup_at"] = now.isoformat()
        row.features_normalized = normalized

        # Notify garage holders that this vehicle sold
        try:
            result = handle_vehicle_sold(db, vin=row.vin, reason="stale_threshold")
            notified_total += result.get("notified_count", 0)
        except Exception:
            logger.warning("vehicle_sold_notification_failed vin=%s", row.vin, exc_info=True)

    marked = len(rows)
    return {
        "dry_run": False,
        "stale_threshold_days": stale_threshold_days,
        "cutoff": cutoff.isoformat(),
        "total_stale_found": total_stale,
        "marked_unavailable": marked,
        "notified_garage_holders": notified_total,
        "capped": total_stale > max_mark,
        "remaining_stale": max(0, total_stale - marked),
    }


def prune_unavailable_ove_inventory(
    db: Session,
    *,
    retention_days: int = 14,
    max_delete: int = 5000,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Delete unavailable OVE rows after a short retention window."""
    cutoff = datetime.now(UTC) - timedelta(days=retention_days)
    prune_filter = [
        func.lower(Vehicle.source_type) == InventorySourceType.OVE.value,
        Vehicle.available.is_(False),
        Vehicle.last_seen_active < cutoff,
    ]

    total_prunable = db.scalar(
        select(func.count()).select_from(Vehicle).where(*prune_filter)
    ) or 0

    if dry_run or total_prunable == 0:
        return {
            "dry_run": dry_run,
            "retention_days": retention_days,
            "cutoff": cutoff.isoformat(),
            "total_prunable_found": total_prunable,
            "deleted": 0,
            "capped": False,
            "remaining_prunable": total_prunable if dry_run else 0,
        }

    vins = [
        row[0]
        for row in db.execute(
            select(Vehicle.vin)
            .where(*prune_filter)
            .order_by(Vehicle.last_seen_active.asc())
            .limit(max_delete)
        ).all()
    ]
    if not vins:
        return {
            "dry_run": False,
            "retention_days": retention_days,
            "cutoff": cutoff.isoformat(),
            "total_prunable_found": total_prunable,
            "deleted": 0,
            "capped": False,
            "remaining_prunable": 0,
        }

    deleted = db.execute(delete(Vehicle).where(Vehicle.vin.in_(vins))).rowcount or 0
    return {
        "dry_run": False,
        "retention_days": retention_days,
        "cutoff": cutoff.isoformat(),
        "total_prunable_found": total_prunable,
        "deleted": deleted,
        "capped": total_prunable > max_delete,
        "remaining_prunable": max(0, total_prunable - deleted),
    }


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
            OveDetailRequest.status.in_(list(_ACTIVE_REQUEST_STATUSES)),
        )
        .order_by(OveDetailRequest.priority.desc(), OveDetailRequest.requested_at.asc())
        .limit(1)
    )
    if existing:
        return existing, True
    # Also dedupe against FAILED requests that are still inside their retry
    # window — we don't want a poke from the UI to short-circuit the backoff.
    failed_existing = db.scalar(
        select(OveDetailRequest)
        .where(
            OveDetailRequest.vin == normalized_vin,
            OveDetailRequest.status == OveDetailRequestStatus.FAILED,
            or_(
                OveDetailRequest.next_retry_at.is_(None),
                OveDetailRequest.next_retry_at > datetime.now(UTC),
            ),
        )
        .order_by(OveDetailRequest.priority.desc(), OveDetailRequest.requested_at.asc())
        .limit(1)
    )
    if failed_existing:
        return failed_existing, True

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


def _enrich_vehicle_from_ove_detail(vehicle: Vehicle, payload: OveDetailPushRequest) -> None:
    """Extract display-critical fields from OVE detail push into Vehicle.features_normalized.

    The listing snapshot hero_facts and sections contain structured key-value
    pairs (e.g. Exterior Color, Interior Color, Transmission, etc.) that the
    frontend needs in features_normalized to avoid showing "N/A".
    """
    normalized = dict(vehicle.features_normalized or {})
    snapshot = payload.listing_snapshot
    cr = payload.condition_report or {}

    # Build a flat lookup from all snapshot sections + hero_facts
    kv: dict[str, str] = {}
    for fact in snapshot.hero_facts:
        label = (fact.get("label") or "").strip().lower()
        value = (fact.get("value") or "").strip()
        if label and value:
            kv[label] = value
    for section in snapshot.sections:
        for item in section.items:
            label = (item.get("label") or item.get("key") or "").strip().lower()
            value = (item.get("value") or "").strip()
            if label and value:
                kv[label] = value

    # Map snapshot fields -> features_normalized keys
    _SNAPSHOT_MAP = {
        "exterior color": "exterior_color",
        "ext color": "exterior_color",
        "ext. color": "exterior_color",
        "interior color": "interior_color",
        "int color": "interior_color",
        "int. color": "interior_color",
        "transmission": "transmission",
        "transmission type": "transmission",
        "trans": "transmission",
        "fuel type": "fuel_type",
        "fuel": "fuel_type",
        "engine": "engine_type",
        "engine type": "engine_type",
        "drivetrain": "drivetrain",
        "drive type": "drivetrain",
        "drive": "drivetrain",
        "body style": "body_type",
        "body type": "body_type",
        "odometer": "odometer_display",
        "mileage": "odometer_display",
        "location": "pickup_location",
        "pickup location": "pickup_location",
        "sale location": "pickup_location",
        "seller": "auction_house",
        "auction": "auction_house",
    }
    for snapshot_key, norm_key in _SNAPSHOT_MAP.items():
        if snapshot_key in kv and not normalized.get(norm_key):
            normalized[norm_key] = kv[snapshot_key]

    # Extract from condition report if available
    if cr.get("overall_grade"):
        normalized["condition_report_grade"] = str(cr["overall_grade"])
    elif cr.get("grade") and not normalized.get("condition_report_grade"):
        normalized["condition_report_grade"] = str(cr["grade"])

    if cr.get("exterior_color") and not normalized.get("exterior_color"):
        normalized["exterior_color"] = str(cr["exterior_color"])
    if cr.get("interior_color") and not normalized.get("interior_color"):
        normalized["interior_color"] = str(cr["interior_color"])

    # Mirror Vehicle column values as fallback
    if vehicle.engine_type and not normalized.get("engine_type"):
        normalized["engine_type"] = vehicle.engine_type
    if vehicle.drivetrain and not normalized.get("drivetrain"):
        normalized["drivetrain"] = vehicle.drivetrain
    if vehicle.body_type and not normalized.get("body_type"):
        normalized["body_type"] = vehicle.body_type
    if vehicle.condition_grade and not normalized.get("condition_report_grade"):
        normalized["condition_report_grade"] = vehicle.condition_grade

    vehicle.features_normalized = normalized


def _image_payload_key(row: OveImagePayload) -> str:
    source_image_id = str(row.source_image_id or "").strip().lower()
    if source_image_id:
        return f"id:{source_image_id}"
    return f"url:{canonical_source_image_url(row.url)}"


def _dedupe_ove_detail_images(images: list[OveImagePayload]) -> tuple[list[OveImagePayload], int]:
    deduped: list[OveImagePayload] = []
    seen: set[str] = set()
    for row in images:
        clean_url = row.url.strip()
        if not clean_url:
            continue
        key = _image_payload_key(row)
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(row)

    saw_primary = False
    normalized: list[OveImagePayload] = []
    for index, row in enumerate(deduped):
        data = row.model_dump()
        data["url"] = row.url.strip()
        data["display_order"] = index
        data["is_primary"] = bool(row.is_primary and not saw_primary)
        if data["is_primary"]:
            saw_primary = True
        normalized.append(OveImagePayload.model_validate(data))

    if normalized and not saw_primary:
        data = normalized[0].model_dump()
        data["is_primary"] = True
        normalized[0] = OveImagePayload.model_validate(data)

    return normalized, max(0, len(images) - len(normalized))


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

    images, removed_image_duplicates = _dedupe_ove_detail_images(payload.images)
    image_urls = [row.url.strip() for row in images if row.url.strip()]
    sync_metadata = dict(payload.sync_metadata or {})
    if removed_image_duplicates:
        sync_metadata["image_dedupe"] = {
            "input_count": len(payload.images),
            "stored_count": len(images),
            "removed_count": removed_image_duplicates,
        }
    raw_payload = payload.model_dump()
    raw_payload["images"] = [row.model_dump() for row in images]
    raw_payload["sync_metadata"] = sync_metadata

    vehicle.images = image_urls or vehicle.images
    vehicle.source_type = InventorySourceType.OVE.value
    if payload.listing_snapshot.page_url:
        vehicle.source_url = payload.listing_snapshot.page_url

    detail.source_platform = payload.source_platform
    detail.seller_comments = payload.seller_comments
    detail.images_json = [row.model_dump() for row in images]
    detail.condition_report_json = payload.condition_report
    detail.listing_snapshot_json = payload.listing_snapshot.model_dump()
    detail.sync_metadata_json = sync_metadata
    detail.raw_payload_json = raw_payload
    detail.page_url = payload.listing_snapshot.page_url
    detail.last_synced_at = datetime.now(UTC)

    # Enrich Vehicle features_normalized from listing snapshot and condition report
    _enrich_vehicle_from_ove_detail(vehicle, payload)

    sync_source_assets(
        db,
        vin=normalized_vin,
        listing_id=vehicle.listing_id,
        image_urls=image_urls,
        source_kind=InventorySourceType.OVE.value,
        source_platform=payload.source_platform,
        deactivate_missing=True,
    )
    chromedata_manifest = build_chromedata_manifest(vehicle, detail_level="card")
    if chromedata_manifest:
        sync_chromedata_source_assets(
            db,
            vehicle=vehicle,
            manifest=chromedata_manifest,
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
            OveDetailRequest.status.in_(list(_ACTIVE_REQUEST_STATUSES)),
        )
        .order_by(OveDetailRequest.requested_at.asc())
    ).all()
    now = datetime.now(UTC)
    for request in completed_requests:
        request.status = OveDetailRequestStatus.COMPLETED
        request.fulfilled_at = now
        request.detail_received_at = now
        request.completed_at = now
        request.leased_to = None
        request.lease_expires_at = None
        request.last_error = None
        request.last_error_category = None
        request.next_retry_at = None

    db.flush()
    return detail, completed_requests, hero_job is not None


def _ensure_aware(value: datetime | None) -> datetime | None:
    """Coerce naive timestamps to UTC-aware datetimes."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def _eligible_for_claim_clause(now: datetime):
    """Build a SQLAlchemy filter expression for requests eligible to be claimed.

    A request is eligible when ANY of:
      - status is PENDING
      - status is FAILED and next_retry_at <= now (or null)
      - status is CLAIMED but its lease has expired
    """
    return or_(
        OveDetailRequest.status == OveDetailRequestStatus.PENDING,
        and_(
            OveDetailRequest.status == OveDetailRequestStatus.FAILED,
            or_(
                OveDetailRequest.next_retry_at.is_(None),
                OveDetailRequest.next_retry_at <= now,
            ),
        ),
        and_(
            OveDetailRequest.status == OveDetailRequestStatus.CLAIMED,
            OveDetailRequest.lease_expires_at.isnot(None),
            OveDetailRequest.lease_expires_at < now,
        ),
    )


def claim_ove_detail_requests(
    db: Session,
    *,
    worker_id: str,
    limit: int,
    lease_seconds: int,
) -> list[OveDetailRequest]:
    """Atomically claim up to ``limit`` eligible detail requests for a worker.

    Uses ``SELECT ... FOR UPDATE SKIP LOCKED`` on Postgres so two workers
    cannot grab the same row.
    """
    worker_id = (worker_id or "").strip()
    if not worker_id:
        raise ValueError("worker_id is required")
    if limit <= 0:
        return []

    now = datetime.now(UTC)
    lease_expires_at = now + timedelta(seconds=lease_seconds)

    stmt = (
        select(OveDetailRequest)
        .where(_eligible_for_claim_clause(now))
        .order_by(
            OveDetailRequest.priority.desc(),
            OveDetailRequest.requested_at.asc(),
            OveDetailRequest.created_at.asc(),
        )
        .limit(limit)
    )

    dialect = db.bind.dialect.name if db.bind is not None else ""
    if dialect != "postgresql":
        raise RuntimeError(f"OVE detail claim requires PostgreSQL, got {dialect or 'unknown'}")
    stmt = stmt.with_for_update(skip_locked=True)

    rows = db.scalars(stmt).all()
    if not rows:
        return []

    claimed: list[OveDetailRequest] = []
    for row in rows:
        # Defensive guard: even with FOR UPDATE, re-check eligibility.
        lease_expires = _ensure_aware(row.lease_expires_at)
        if row.status == OveDetailRequestStatus.CLAIMED and (
            lease_expires is None or lease_expires >= now
        ):
            continue
        if row.status in _TERMINAL_REQUEST_STATUSES:
            continue
        row.status = OveDetailRequestStatus.CLAIMED
        row.leased_to = worker_id
        row.claimed_at = now
        row.lease_expires_at = lease_expires_at
        row.last_polled_at = now
        row.attempts = (row.attempts or 0) + 1
        claimed.append(row)

    db.flush()
    return claimed


def _load_request_for_worker(
    db: Session,
    *,
    request_id: str,
    worker_id: str,
) -> OveDetailRequest:
    request = db.get(OveDetailRequest, request_id)
    if request is None:
        raise OveDetailRequestNotFoundError(f"OVE detail request {request_id} not found")
    if request.status != OveDetailRequestStatus.CLAIMED:
        raise OveDetailRequestStateError(
            f"Request {request_id} is not currently claimed (status={request.status.value})"
        )
    if request.leased_to != worker_id:
        raise OveDetailRequestOwnershipError(
            f"Request {request_id} is leased to {request.leased_to}, not {worker_id}"
        )
    return request


def complete_ove_detail_request(
    db: Session,
    *,
    request_id: str,
    worker_id: str,
    result: str = "success",
) -> OveDetailRequest:
    request = _load_request_for_worker(db, request_id=request_id, worker_id=worker_id)
    now = datetime.now(UTC)
    request.status = OveDetailRequestStatus.COMPLETED
    request.completed_at = now
    request.fulfilled_at = now
    request.detail_received_at = now
    request.leased_to = None
    request.lease_expires_at = None
    request.last_error = None
    request.last_error_category = None
    request.next_retry_at = None
    metadata = dict(request.metadata_json or {})
    metadata["last_result"] = result
    request.metadata_json = metadata
    db.flush()
    return request


def fail_ove_detail_request(
    db: Session,
    *,
    request_id: str,
    worker_id: str,
    error_category: str,
    error_message: str | None,
    retry_after_seconds: int,
) -> OveDetailRequest:
    request = _load_request_for_worker(db, request_id=request_id, worker_id=worker_id)
    now = datetime.now(UTC)
    request.status = OveDetailRequestStatus.FAILED
    request.last_error = error_message
    request.last_error_category = error_category
    request.next_retry_at = now + timedelta(seconds=max(0, retry_after_seconds))
    request.leased_to = None
    request.lease_expires_at = None
    db.flush()
    return request


def terminal_ove_detail_request(
    db: Session,
    *,
    request_id: str,
    worker_id: str,
    reason: str,
    message: str | None,
) -> OveDetailRequest:
    request = _load_request_for_worker(db, request_id=request_id, worker_id=worker_id)
    now = datetime.now(UTC)
    request.status = OveDetailRequestStatus.TERMINAL
    request.terminal_reason = reason
    request.terminal_message = message
    request.completed_at = now
    request.leased_to = None
    request.lease_expires_at = None
    request.next_retry_at = None
    db.flush()
    return request


def heartbeat_ove_detail_request(
    db: Session,
    *,
    request_id: str,
    worker_id: str,
    lease_seconds: int,
) -> OveDetailRequest:
    request = _load_request_for_worker(db, request_id=request_id, worker_id=worker_id)
    now = datetime.now(UTC)
    request.lease_expires_at = now + timedelta(seconds=lease_seconds)
    request.last_polled_at = now
    db.flush()
    return request


def serialize_request_timestamp(value: datetime | None) -> str | None:
    if value is None:
        return None
    normalized = value if value.tzinfo else value.replace(tzinfo=UTC)
    return normalized.astimezone(UTC).isoformat()


# ---------------------------------------------------------------------------
# Scraper heartbeat + health snapshot
# ---------------------------------------------------------------------------


def upsert_scraper_heartbeat(
    db: Session,
    *,
    worker_id: str,
    profile: str | None = None,
    scraper_version: str | None = None,
    node_id: str | None = None,
    last_sync_at: datetime | None = None,
    last_poll_at: datetime | None = None,
    last_claim_at: datetime | None = None,
    pending_claims: int | None = None,
    status_note: str | None = None,
    details: dict[str, Any] | None = None,
) -> OveScraperHeartbeat:
    """Upsert a heartbeat row for the given worker. One row per worker_id;
    older fields are only overwritten when the caller provides a new value,
    so a minimal heartbeat never clobbers richer state from an earlier call.
    """
    now = datetime.now(UTC)
    row = db.get(OveScraperHeartbeat, worker_id)
    if row is None:
        row = OveScraperHeartbeat(
            worker_id=worker_id,
            profile=profile,
            scraper_version=scraper_version,
            node_id=node_id,
            last_heartbeat_at=now,
            last_sync_at=last_sync_at,
            last_poll_at=last_poll_at,
            last_claim_at=last_claim_at,
            pending_claims=pending_claims,
            status_note=status_note,
            details_json=details or {},
        )
        db.add(row)
    else:
        row.last_heartbeat_at = now
        if profile is not None:
            row.profile = profile
        if scraper_version is not None:
            row.scraper_version = scraper_version
        if node_id is not None:
            row.node_id = node_id
        if last_sync_at is not None:
            row.last_sync_at = last_sync_at
        if last_poll_at is not None:
            row.last_poll_at = last_poll_at
        if last_claim_at is not None:
            row.last_claim_at = last_claim_at
        if pending_claims is not None:
            row.pending_claims = pending_claims
        if status_note is not None:
            row.status_note = status_note
        if details is not None:
            row.details_json = details
    db.flush()
    return row


def get_ove_inventory_health(
    db: Session,
    *,
    stale_warning_minutes: int,
    stale_critical_minutes: int,
    heartbeat_warning_minutes: int,
    heartbeat_critical_minutes: int,
) -> dict[str, Any]:
    """Build the operational health snapshot used by /inventory/ove/health.

    Combines inventory freshness (max ``vehicles.updated_at`` among active
    OVE rows), the detail-request queue backlog, and the most recent
    scraper heartbeat into a single traffic-light payload.
    """
    now = datetime.now(UTC)

    # Inventory freshness — use the most recent updated_at on active OVE
    # rows as a proxy for 'last full snapshot observed'. Ingest replaces
    # rows in bulk so this lines up with the latest snapshot.
    inv_row = db.execute(
        select(
            func.count(Vehicle.vin).filter(Vehicle.available.is_(True)),
            func.count(Vehicle.vin).filter(Vehicle.available.is_(False)),
            func.max(Vehicle.updated_at).filter(Vehicle.available.is_(True)),
        ).where(Vehicle.source_type == InventorySourceType.OVE.value)
    ).one()
    available_count = int(inv_row[0] or 0)
    unavailable_count = int(inv_row[1] or 0)
    last_snapshot_at = inv_row[2]

    minutes_since_snapshot: float | None = None
    if last_snapshot_at is not None:
        normalized = last_snapshot_at if last_snapshot_at.tzinfo else last_snapshot_at.replace(tzinfo=UTC)
        minutes_since_snapshot = max(0.0, (now - normalized).total_seconds() / 60.0)

    # Detail request queue summary
    queue_row = db.execute(
        select(OveDetailRequest.status, func.count(OveDetailRequest.id)).group_by(OveDetailRequest.status)
    ).all()
    queue_counts = {status.value: 0 for status in OveDetailRequestStatus}
    for status, count in queue_row:
        queue_counts[status.value] = int(count)

    # Latest heartbeat across all workers
    hb_row = db.execute(
        select(OveScraperHeartbeat).order_by(OveScraperHeartbeat.last_heartbeat_at.desc()).limit(1)
    ).scalar_one_or_none()

    heartbeat_payload: dict[str, Any] | None = None
    minutes_since_heartbeat: float | None = None
    if hb_row is not None:
        hb_ts = hb_row.last_heartbeat_at
        hb_ts = hb_ts if hb_ts.tzinfo else hb_ts.replace(tzinfo=UTC)
        minutes_since_heartbeat = max(0.0, (now - hb_ts).total_seconds() / 60.0)
        heartbeat_payload = {
            "worker_id": hb_row.worker_id,
            "profile": hb_row.profile,
            "scraper_version": hb_row.scraper_version,
            "node_id": hb_row.node_id,
            "last_heartbeat_at": serialize_request_timestamp(hb_row.last_heartbeat_at),
            "last_sync_at": serialize_request_timestamp(hb_row.last_sync_at),
            "last_poll_at": serialize_request_timestamp(hb_row.last_poll_at),
            "last_claim_at": serialize_request_timestamp(hb_row.last_claim_at),
            "pending_claims": hb_row.pending_claims,
            "status_note": hb_row.status_note,
            "minutes_since_heartbeat": round(minutes_since_heartbeat, 2),
        }

    def _level(minutes: float | None, warn: int, crit: int) -> str:
        if minutes is None:
            return "unknown"
        if minutes >= crit:
            return "critical"
        if minutes >= warn:
            return "warning"
        return "ok"

    snapshot_level = _level(minutes_since_snapshot, stale_warning_minutes, stale_critical_minutes)
    heartbeat_level = _level(minutes_since_heartbeat, heartbeat_warning_minutes, heartbeat_critical_minutes)

    # Overall status is the worst of the two subsystems. "unknown" is
    # treated as worse than "ok" but better than "warning" — it means we
    # have never seen a signal, which is expected right after deploy.
    rank = {"ok": 0, "unknown": 1, "warning": 2, "critical": 3}
    overall_level = max([snapshot_level, heartbeat_level], key=lambda lvl: rank[lvl])

    return {
        "overall": overall_level,
        "now": serialize_request_timestamp(now),
        "inventory": {
            "last_snapshot_at": serialize_request_timestamp(last_snapshot_at),
            "minutes_since_snapshot": round(minutes_since_snapshot, 2) if minutes_since_snapshot is not None else None,
            "available_count": available_count,
            "unavailable_count": unavailable_count,
            "level": snapshot_level,
            "warning_threshold_minutes": stale_warning_minutes,
            "critical_threshold_minutes": stale_critical_minutes,
        },
        "queue": {
            "pending": queue_counts.get("PENDING", 0),
            "claimed": queue_counts.get("CLAIMED", 0),
            "in_progress": queue_counts.get("IN_PROGRESS", 0),
            "failed": queue_counts.get("FAILED", 0),
            "completed": queue_counts.get("COMPLETED", 0),
            "terminal": queue_counts.get("TERMINAL", 0),
            "canceled": queue_counts.get("CANCELED", 0),
        },
        "scraper": {
            "level": heartbeat_level,
            "warning_threshold_minutes": heartbeat_warning_minutes,
            "critical_threshold_minutes": heartbeat_critical_minutes,
            "latest": heartbeat_payload,
        },
    }
