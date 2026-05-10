from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.integrations.marketcheck_client import MarketCheckClient
from app.core.constants import InventorySourceType
from app.models.entities import Vehicle
import logging

from app.services.image_pipeline_service import ensure_tier2_hero_job, sync_marketcheck_source_assets

logger = logging.getLogger(__name__)


MOCK_VEHICLES = [
    {
        "vin": "1FMCU9H9XNUA00001",
        "listing_id": "mk-001",
        "year": 2022,
        "make": "Ford",
        "model": "Escape",
        "trim": "SEL",
        "body_type": "SUV",
        "engine_type": "Hybrid",
        "drivetrain": "AWD",
        "condition_grade": "Good",
        "price_asking": 25995,
        "location_zip": "33445",
        "location_state": "FL",
        "source_type": "dealer_partner",
        "features_raw": ["Apple CarPlay", "Blind Spot Monitor", "Lane Keep Assist"],
        "features_normalized": {"safety": 0.9, "tech": 0.8, "fuel economy": 0.85},
    },
    {
        "vin": "5NMS3DAJ9PH000002",
        "listing_id": "mk-002",
        "year": 2023,
        "make": "Hyundai",
        "model": "Santa Fe",
        "trim": "Limited",
        "body_type": "SUV",
        "engine_type": "Gasoline",
        "drivetrain": "AWD",
        "condition_grade": "Excellent",
        "price_asking": 31490,
        "location_zip": "33101",
        "location_state": "FL",
        "source_type": "dealer_wholesale",
        "features_raw": ["360 Camera", "Panoramic Roof", "Highway Assist"],
        "features_normalized": {"safety": 0.95, "tech": 0.9, "luxury": 0.7},
    },
    {
        "vin": "1C6SRFJT0PN000003",
        "listing_id": "mk-003",
        "year": 2023,
        "make": "Ram",
        "model": "1500",
        "trim": "Laramie",
        "body_type": "Truck",
        "engine_type": "Gasoline",
        "drivetrain": "4WD",
        "condition_grade": "Good",
        "price_asking": 43995,
        "location_zip": "32801",
        "location_state": "FL",
        "source_type": "auction",
        "features_raw": ["Tow Package", "Trailer Brake", "Apple CarPlay"],
        "features_normalized": {"towing": 0.95, "cargo": 0.8, "tech": 0.75},
    },
    {
        "vin": "WAUENAF48KN000004",
        "listing_id": "mk-004",
        "year": 2019,
        "make": "Audi",
        "model": "A4",
        "trim": "Premium",
        "body_type": "Sedan",
        "engine_type": "Gasoline",
        "drivetrain": "AWD",
        "condition_grade": "Good",
        "price_asking": 23950,
        "location_zip": "33602",
        "location_state": "FL",
        "source_type": "dealer_partner",
        "features_raw": ["Leather", "Sunroof", "Sport Package"],
        "features_normalized": {"luxury": 0.9, "sportiness": 0.8, "tech": 0.7},
    },
    {
        "vin": "7SAYGDEF4PF000005",
        "listing_id": "mk-005",
        "year": 2023,
        "make": "Tesla",
        "model": "Model Y",
        "trim": "Long Range",
        "body_type": "SUV",
        "engine_type": "BEV",
        "drivetrain": "AWD",
        "condition_grade": "Excellent",
        "price_asking": 37990,
        "location_zip": "34741",
        "location_state": "FL",
        "source_type": "dealer_wholesale",
        "features_raw": ["Autopilot", "OTA Updates", "Premium Audio"],
        "features_normalized": {"tech": 0.95, "safety": 0.9, "fuel economy": 1.0},
    },
]


SOURCE_PRIORITY: dict[str, int] = {
    InventorySourceType.MARKETCHECK.value: 1,
    InventorySourceType.DEALER_PARTNER.value: 2,
    InventorySourceType.DEALER_WHOLESALE.value: 2,
    InventorySourceType.AUCTION.value: 3,
    InventorySourceType.OVE.value: 4,
}

# Fields that change between MarketCheck snapshots and must always be refreshed.
_MC_VOLATILE_FIELDS = (
    "listing_id",
    "odometer",
    "price_asking",
    "price_wholesale_est",
    "location_zip",
    "location_state",
    "condition_grade",
    "source_url",
)

PRIMARY_SOURCE_FIELDS = (
    "listing_id",
    "year",
    "make",
    "model",
    "trim",
    "body_type",
    "sub_body_type",
    "engine_type",
    "cylinders",
    "forced_induction",
    "drivetrain",
    "mpg_combined",
    "ev_range",
    "towing_capacity_lbs",
    "odometer",
    "condition_grade",
    "price_asking",
    "price_wholesale_est",
    "location_zip",
    "location_state",
    "source_url",
    "images",
    "features_raw",
    "features_normalized",
    "quality_firewall_pass",
)

SECONDARY_FILL_FIELDS = (
    "listing_id",
    "trim",
    "body_type",
    "sub_body_type",
    "engine_type",
    "cylinders",
    "forced_induction",
    "drivetrain",
    "mpg_combined",
    "ev_range",
    "towing_capacity_lbs",
    "odometer",
    "condition_grade",
    "price_wholesale_est",
    "location_zip",
    "location_state",
    "source_url",
    "images",
    "features_raw",
    "features_normalized",
)


@dataclass(slots=True)
class InventoryIngestReport:
    source: str
    fetched: int = 0
    inserted: int = 0
    updated: int = 0
    skipped_priority: int = 0
    skipped_invalid: int = 0
    mode: str = "live"
    synced_vins: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def seed_inventory(db: Session) -> int:
    count = 0
    for row in MOCK_VEHICLES:
        existing = db.get(Vehicle, row["vin"])
        if existing:
            continue
        vehicle = Vehicle(
            **row,
            available=True,
            quality_firewall_pass=True,
            last_seen_active=datetime.now(UTC),
        )
        db.add(vehicle)
        count += 1
    db.flush()
    return count


def ingest_marketcheck_inventory(
    db: Session,
    client: MarketCheckClient,
    *,
    limit: int = 100,
    start: int = 0,
    search_params: dict[str, Any] | None = None,
) -> InventoryIngestReport:
    report = InventoryIngestReport(
        source="marketcheck",
        fetched=0,
        mode="live" if client.live else "stub",
    )
    now = datetime.now(UTC)
    filtered_params = {k: v for k, v in (search_params or {}).items() if v not in (None, "")}
    remaining = max(1, int(limit))
    cursor = max(0, int(start))
    page_guard = 0
    # Some MarketCheck plans cap per-call rows lower than requested; page forward until exhausted.
    while remaining > 0 and page_guard < 100:
        batch_rows = min(remaining, 100)
        params: dict[str, Any] = {"rows": batch_rows, "start": cursor}
        params.update(filtered_params)

        payload = client.search_inventory(params)
        listings = payload.get("listings", [])
        if not isinstance(listings, list):
            listings = []
        if not listings:
            break

        report.fetched += len(listings)

        for raw_listing in listings:
            if not isinstance(raw_listing, dict):
                report.skipped_invalid += 1
                continue

            normalized = normalize_marketcheck_listing(raw_listing, now=now)
            if not normalized:
                report.skipped_invalid += 1
                continue

            existing = db.get(Vehicle, normalized["vin"])
            action = upsert_vehicle_with_source_priority(
                existing=existing,
                incoming=normalized,
                incoming_source="marketcheck",
            )
            if action == "inserted":
                db.add(Vehicle(**normalized))
                report.inserted += 1
            elif action == "updated":
                report.updated += 1
            else:
                report.skipped_priority += 1
            vin = normalized["vin"]
            if vin not in report.synced_vins:
                report.synced_vins.append(vin)

            # Tier 4-ready model keeps source cache records independent from vehicle row shape.
            images = normalized.get("images") or []
            sync_marketcheck_source_assets(
                db,
                vin=normalized["vin"],
                listing_id=normalized.get("listing_id"),
                image_urls=images,
            )
            ensure_tier2_hero_job(
                db,
                vin=normalized["vin"],
                trigger_event="marketcheck_ingest",
                primary_image_url=images[0] if images else None,
            )

        got = len(listings)
        remaining -= got
        cursor += got
        page_guard += 1

        num_found = payload.get("num_found")
        if isinstance(num_found, int) and cursor >= num_found:
            break

    db.flush()
    return report


def run_marketcheck_daily_snapshot(
    db: Session,
    *,
    client: MarketCheckClient,
    target_states: list[str],
    limit_per_state: int,
    min_dom: int,
    min_year: int,
    min_miles: int,
    max_miles: int,
) -> dict[str, Any]:
    """Prefetch MarketCheck inventory for configured target states.

    `ingest_marketcheck_inventory` already paginates internally. Call it once
    per state with a high limit to avoid double-pagination and duplicate calls.
    """
    total = InventoryIngestReport(source="marketcheck_snapshot")
    state_results: dict[str, dict[str, Any]] = {}
    normalized_states = [state.strip().upper() for state in target_states if state.strip()]

    for state in normalized_states:
        search_params = {
            "state": state,
            "inventory_type": "used",
            "car_type": "used",
            "dom_range": f"{max(0, min_dom)}-9999",
            "year_range": f"{max(1900, min_year)}-{datetime.now(UTC).year + 1}",
            "miles_range": f"{max(0, min_miles)}-{max(max_miles, min_miles)}",
        }
        try:
            report = ingest_marketcheck_inventory(
                db,
                client=client,
                limit=max(1, limit_per_state),
                start=0,
                search_params=search_params,
            )
            db.commit()
        except Exception as exc:
            db.rollback()
            logger.warning("marketcheck_snapshot_state_failed state=%s", state, exc_info=True)
            state_results[state] = {"status": "error", "error": str(exc)}
            continue

        total.fetched += report.fetched
        total.inserted += report.inserted
        total.updated += report.updated
        total.skipped_priority += report.skipped_priority
        total.skipped_invalid += report.skipped_invalid
        state_results[state] = {"status": "ok", **report.to_dict()}

    return {
        "source": "marketcheck_snapshot",
        "states_requested": normalized_states,
        "states": state_results,
        "total": total.to_dict(),
    }


def cleanup_stale_marketcheck_inventory(
    db: Session,
    *,
    stale_threshold_days: int = 7,
    max_mark: int = 5000,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Mark stale MarketCheck vehicles unavailable without touching auction feeds."""
    cutoff = datetime.now(UTC) - timedelta(days=max(1, stale_threshold_days))
    now = datetime.now(UTC)
    stale_filter = [
        func.lower(Vehicle.source_type) == InventorySourceType.MARKETCHECK.value,
        Vehicle.available.is_(True),
        Vehicle.last_seen_active < cutoff,
    ]
    total_stale = db.scalar(select(func.count()).select_from(Vehicle).where(*stale_filter)) or 0

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
        .limit(max(1, max_mark))
    ).all()

    for row in rows:
        row.available = False
        normalized = dict(row.features_normalized or {})
        normalized["status"] = "Unavailable"
        normalized["cleanup_reason"] = "marketcheck_stale_threshold"
        normalized["cleanup_at"] = now.isoformat()
        row.features_normalized = normalized

    marked = len(rows)
    return {
        "dry_run": False,
        "stale_threshold_days": stale_threshold_days,
        "cutoff": cutoff.isoformat(),
        "total_stale_found": total_stale,
        "marked_unavailable": marked,
        "capped": total_stale > max_mark,
        "remaining_stale": max(0, total_stale - marked),
    }


def upsert_vehicle_with_source_priority(
    *,
    existing: Vehicle | None,
    incoming: dict[str, Any],
    incoming_source: str,
) -> str:
    if existing is None:
        return "inserted"

    incoming_priority = SOURCE_PRIORITY.get(incoming_source, 0)
    existing_priority = SOURCE_PRIORITY.get((existing.source_type or "").lower(), 0)
    now = incoming.get("last_seen_active") or datetime.now(UTC)

    # MarketCheck reactivation: when a previously-seen MarketCheck VIN
    # reappears, only refresh volatile fields (price, odometer, location)
    # and preserve enrichment data we already collected (images, features,
    # specs).  This avoids redundant API calls for VINs we've enriched.
    existing_is_mc = (existing.source_type or "").lower() == InventorySourceType.MARKETCHECK.value
    incoming_is_mc = incoming_source == InventorySourceType.MARKETCHECK.value
    if existing_is_mc and incoming_is_mc:
        for field in _MC_VOLATILE_FIELDS:
            value = incoming.get(field)
            if value is not None:
                setattr(existing, field, value)
        # Back-fill stable fields only when the existing row lacks them.
        for field in PRIMARY_SOURCE_FIELDS:
            if field in _MC_VOLATILE_FIELDS:
                continue
            current = getattr(existing, field, None)
            if is_missing_value(current):
                value = incoming.get(field)
                if not is_missing_value(value):
                    setattr(existing, field, value)
        existing.available = True
        existing.last_seen_active = now
        return "updated"

    if incoming_priority >= existing_priority:
        for field in PRIMARY_SOURCE_FIELDS:
            value = incoming.get(field)
            if value is not None:
                setattr(existing, field, value)
        existing.source_type = incoming_source
        existing.available = bool(incoming.get("available", existing.available))
        existing.last_seen_active = now
        return "updated"

    # Lower-priority source should not overwrite higher-priority rows.
    for field in SECONDARY_FILL_FIELDS:
        current = getattr(existing, field)
        if is_missing_value(current):
            value = incoming.get(field)
            if not is_missing_value(value):
                setattr(existing, field, value)
    existing.last_seen_active = now
    existing.available = existing.available and bool(incoming.get("available", True))
    return "skipped_priority"


def normalize_marketcheck_listing(raw: dict[str, Any], *, now: datetime | None = None) -> dict[str, Any] | None:
    build = raw.get("build") if isinstance(raw.get("build"), dict) else {}
    seller = raw.get("dealer") if isinstance(raw.get("dealer"), dict) else {}
    if not seller:
        seller = raw.get("seller") if isinstance(raw.get("seller"), dict) else {}
    media = raw.get("media") if isinstance(raw.get("media"), dict) else {}
    extra = raw.get("extra") if isinstance(raw.get("extra"), dict) else {}

    vin = clean_str(raw.get("vin"))
    year = to_int(pick_first(build.get("year"), raw.get("year")))
    make = clean_str(pick_first(build.get("make"), raw.get("make")))
    model = clean_str(pick_first(build.get("model"), raw.get("model")))
    price = to_float(
        pick_first(
            raw.get("price"),
            raw.get("price_unformatted"),
            raw.get("msrp"),
            raw.get("seller_price"),
        )
    )

    if not vin or len(vin) != 17 or year is None or make is None or model is None or price is None:
        return None

    listing_id = clean_str(
        pick_first(
            raw.get("id"),
            raw.get("listing_id"),
            raw.get("inventory_id"),
            raw.get("_id"),
        )
    )
    location_state = clean_str(pick_first(seller.get("state"), raw.get("state")))
    if location_state:
        location_state = location_state.upper()[:2]

    images = safe_list(
        pick_first(
            raw.get("photo_links_cached"),
            media.get("photo_links_cached"),
            raw.get("photo_links"),
            media.get("photo_links"),
            raw.get("images"),
        )
    )
    options = safe_list(extra.get("options"))
    high_value_features = safe_list(extra.get("high_value_features"))
    features = safe_list(
        pick_first(
            extra.get("features"),
            raw.get("features"),
            high_value_features,
            options,
        )
    )

    exterior_color = clean_str(
        pick_first(
            raw.get("exterior_color"),
            extra.get("exterior_color"),
            raw.get("base_ext_color"),
        )
    )
    interior_color = clean_str(
        pick_first(
            raw.get("interior_color"),
            extra.get("interior_color"),
            raw.get("base_int_color"),
        )
    )
    transmission = clean_str(pick_first(build.get("transmission"), raw.get("transmission")))
    fuel_type = clean_str(pick_first(build.get("fuel_type"), raw.get("fuel_type")))
    inventory_type = clean_str(raw.get("inventory_type"))
    days_on_market = to_int(pick_first(raw.get("dom"), raw.get("dom_active"), raw.get("dom_180")))
    city_mpg = to_float(
        pick_first(
            build.get("city_mpg"),
            raw.get("city_mpg"),
            raw.get("mpg_city"),
            raw.get("city_miles_per_gallon"),
            raw.get("mpgCity"),
            raw.get("epa_city_mpg"),
        )
    )
    highway_mpg = to_float(
        pick_first(
            build.get("highway_mpg"),
            raw.get("highway_mpg"),
            raw.get("mpg_highway"),
            raw.get("highway_miles_per_gallon"),
            raw.get("mpgHighway"),
            raw.get("epa_highway_mpg"),
        )
    )
    combined_mpg = to_float(
        pick_first(
            build.get("combined_mpg"),
            raw.get("combined_mpg"),
            raw.get("mpg_combined"),
            raw.get("mpg"),
            raw.get("epa_combined_mpg"),
        )
    )
    if combined_mpg is None and city_mpg is not None and highway_mpg is not None:
        combined_mpg = round((city_mpg + highway_mpg) / 2.0, 1)
    certified = to_bool(raw.get("certified"))
    single_owner = to_bool(raw.get("carfax_1_owner"))
    clean_title = to_bool(raw.get("carfax_clean_title"))
    city = clean_str(pick_first(seller.get("city"), raw.get("city")))
    dealer_name = clean_str(pick_first(seller.get("name"), raw.get("dealer_name"), raw.get("heading")))

    normalized = {
        "vin": vin.upper(),
        "listing_id": listing_id,
        "year": year,
        "make": make,
        "model": model,
        "trim": clean_str(pick_first(build.get("trim"), raw.get("trim"))),
        "body_type": clean_str(pick_first(build.get("body_type"), raw.get("body_type"), raw.get("vehicle_type"))),
        "sub_body_type": clean_str(pick_first(build.get("vehicle_type"), raw.get("sub_body_type"))),
        "engine_type": clean_str(pick_first(build.get("engine"), raw.get("engine"), build.get("fuel_type"))),
        "cylinders": to_int(pick_first(build.get("cylinders"), raw.get("cylinders"))),
        "forced_induction": clean_str(pick_first(build.get("forced_induction"), raw.get("forced_induction"))),
        "drivetrain": clean_str(pick_first(build.get("drivetrain"), raw.get("drivetrain"))),
        "mpg_combined": combined_mpg,
        "ev_range": to_int(pick_first(build.get("ev_range"), raw.get("ev_range"))),
        "towing_capacity_lbs": to_int(pick_first(build.get("towing_capacity"), raw.get("towing_capacity_lbs"))),
        "odometer": to_int(pick_first(raw.get("miles"), raw.get("odometer"))),
        "condition_grade": clean_str(pick_first(raw.get("condition"), raw.get("condition_grade"))),
        "price_asking": price,
        "price_wholesale_est": to_float(raw.get("wholesale_price")),
        "location_zip": clean_str(pick_first(seller.get("zip"), raw.get("zip"))),
        "location_state": location_state,
        "source_type": "marketcheck",
        "source_url": clean_str(pick_first(raw.get("vdp_url"), raw.get("listing_url"), raw.get("website"))),
        "images": [str(x) for x in images if x],
        "features_raw": [str(x) for x in features if x],
        "features_normalized": {
            "exterior_color": exterior_color,
            "interior_color": interior_color,
            "transmission": transmission,
            "fuel_type": fuel_type,
            "city_mpg": city_mpg,
            "highway_mpg": highway_mpg,
            "inventory_type": inventory_type,
            "days_on_market": days_on_market,
            "certified": certified,
            "single_owner": single_owner,
            "clean_title": clean_title,
            "city": city,
            "dealer_name": dealer_name,
        },
        "last_seen_active": now or datetime.now(UTC),
        "available": bool(pick_first(raw.get("active"), True)),
        "quality_firewall_pass": True,
    }
    return normalized


def pick_first(*values: Any) -> Any:
    for value in values:
        if value not in (None, "", [], {}):
            return value
    return None


def to_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def to_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def to_bool(value: Any) -> bool | None:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y"}:
        return True
    if text in {"0", "false", "no", "n"}:
        return False
    return None


def clean_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def safe_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return []


def is_missing_value(value: Any) -> bool:
    return value in (None, "", [], {})
