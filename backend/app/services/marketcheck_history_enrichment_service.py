from __future__ import annotations

import ast
import logging
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.integrations.marketcheck_client import MarketCheckClient
from app.models.entities import Vehicle, VehicleHistoryEnrichment
from app.services.seller_comment_service import build_virtualcarhub_seller_comment

logger = logging.getLogger(__name__)

ENRICHABLE_SOURCE_TYPES = {"auction", "ove"}
ENRICHMENT_FILL_KEYS = (
    "exterior_color",
    "interior_color",
    "transmission",
    "fuel_type",
    "inventory_type",
    "days_on_market",
    "certified",
    "single_owner",
    "clean_title",
    "dealer_name",
    "city",
)


def build_marketcheck_client() -> MarketCheckClient:
    return MarketCheckClient(
        api_key=settings.marketcheck_api_key,
        api_secret=settings.marketcheck_api_secret,
        price_api_key=settings.marketcheck_price_api_key,
        api_base_url=settings.marketcheck_api_base_url,
        live=settings.has_marketcheck,
    )


def _to_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _to_bool(value: Any) -> bool | None:
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


def _to_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _safe_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    return []


def _coerce_feature_mapping(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        return value
    text = _to_str(value)
    if not text or not text.startswith("{") or not text.endswith("}"):
        return None
    try:
        parsed = ast.literal_eval(text)
    except (ValueError, SyntaxError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _split_feature_text(value: str | None) -> tuple[str | None, str | None]:
    text = _to_str(value)
    if not text:
        return None, None

    if "@" not in text:
        return None, text

    prefix, remainder = text.split("@", 1)
    category = _to_str(prefix)
    description = _to_str(remainder)
    if not category or not description:
        return None, text

    normalized = category.lower()
    known_categories = {
        "comfort & convenience",
        "engine",
        "exterior",
        "infotainment",
        "interior",
        "packages",
        "performance",
        "safety & driver assist",
        "technology",
        "transmission",
        "vehicle segment",
    }
    if normalized not in known_categories:
        return None, text

    return category, description


def _normalize_feature_detail(value: Any) -> dict[str, str | None] | None:
    mapping = _coerce_feature_mapping(value)
    if mapping is not None:
        raw_description = _to_str(
            mapping.get("description")
            or mapping.get("name")
            or mapping.get("feature")
            or mapping.get("value")
        )
        if not raw_description:
            return None
        category = _to_str(mapping.get("category"))
        split_category, description = _split_feature_text(raw_description)
        if not description:
            return None
        return {
            "category": category or split_category,
            "description": description,
            "type": _to_str(mapping.get("type")),
        }

    text = _to_str(value)
    if not text:
        return None
    category, description = _split_feature_text(text)
    return {"category": category, "description": description or text, "type": None}


def _normalize_feature_details(values: Any) -> list[dict[str, str | None]]:
    if not isinstance(values, list):
        return []
    out: list[dict[str, str | None]] = []
    seen: set[str] = set()
    for value in values:
        item = _normalize_feature_detail(value)
        if not item:
            continue
        key = "|".join(
            [
                (item.get("category") or "").strip().lower(),
                (item.get("description") or "").strip().lower(),
                (item.get("type") or "").strip().lower(),
            ]
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def extract_listing_metadata(listing: dict[str, Any] | None) -> dict[str, Any]:
    listing = listing or {}
    build = listing.get("build") if isinstance(listing.get("build"), dict) else {}
    extra = listing.get("extra") if isinstance(listing.get("extra"), dict) else {}
    dealer = listing.get("dealer") if isinstance(listing.get("dealer"), dict) else {}
    media = listing.get("media") if isinstance(listing.get("media"), dict) else {}

    features = _normalize_feature_details(extra.get("features") or listing.get("features") or [])
    high_value = _normalize_feature_details(extra.get("high_value_features") or [])
    options = _normalize_feature_details(extra.get("options") or [])
    option_packages = _normalize_feature_details(extra.get("options_packages") or [])

    merged_feature_details: list[dict[str, str | None]] = []
    seen: set[str] = set()
    for source in (features, high_value, options, option_packages):
        for item in source:
            description = item.get("description")
            if not description:
                continue
            key = description.lower()
            if key in seen:
                continue
            seen.add(key)
            merged_feature_details.append(item)

    photo_links = [str(item) for item in _safe_list(media.get("photo_links")) if _to_str(item)]
    photo_links_cached = [str(item) for item in _safe_list(media.get("photo_links_cached")) if _to_str(item)]

    return {
        "exterior_color": _to_str(
            listing.get("exterior_color")
            or extra.get("exterior_color")
            or listing.get("base_ext_color")
        ),
        "interior_color": _to_str(
            listing.get("interior_color")
            or extra.get("interior_color")
            or listing.get("base_int_color")
        ),
        "transmission": _to_str(build.get("transmission") or listing.get("transmission")),
        "fuel_type": _to_str(build.get("fuel_type") or listing.get("fuel_type")),
        "inventory_type": _to_str(listing.get("inventory_type") or extra.get("inventory_type")),
        "days_on_market": _to_int(listing.get("dom") or listing.get("dom_active") or listing.get("dom_180")),
        "certified": _to_bool(listing.get("certified")),
        "single_owner": _to_bool(listing.get("carfax_1_owner")),
        "clean_title": _to_bool(listing.get("carfax_clean_title")),
        "description": _to_str(
            extra.get("seller_comments")
            or listing.get("seller_comments")
            or extra.get("description")
            or listing.get("description")
        ),
        "seller_comments": _to_str(extra.get("seller_comments") or listing.get("seller_comments")),
        "dealer_name": _to_str(dealer.get("name") or listing.get("mc_dealership") or listing.get("heading")),
        "city": _to_str(dealer.get("city") or listing.get("city")),
        "source_url": _to_str(listing.get("vdp_url") or listing.get("listing_url") or listing.get("website")),
        "photo_links": photo_links,
        "photo_links_cached": photo_links_cached,
        "supplemental_photo_links": list(dict.fromkeys([*photo_links_cached, *photo_links])),
        "features": [item["description"] for item in merged_feature_details if item.get("description")],
        "feature_details": merged_feature_details,
        "high_value_features": [item["description"] for item in high_value if item.get("description")],
        "high_value_feature_details": high_value,
        "options": [item["description"] for item in options if item.get("description")],
        "option_details": options,
        "option_packages": [item["description"] for item in option_packages if item.get("description")],
        "option_package_codes": [item["description"] for item in option_packages if item.get("description")],
        "option_package_details": option_packages,
    }


def merge_listing_metadata(primary: dict[str, Any] | None, secondary: dict[str, Any] | None) -> dict[str, Any]:
    merged = dict(secondary or {})
    merged.update({k: v for k, v in (primary or {}).items() if v not in (None, "", [], {})})

    list_keys = (
        "features",
        "high_value_features",
        "options",
        "option_packages",
        "option_package_codes",
        "photo_links",
        "photo_links_cached",
        "supplemental_photo_links",
        "feature_details",
        "high_value_feature_details",
        "option_details",
        "option_package_details",
    )
    for key in list_keys:
        combined: list[Any] = []
        seen: set[str] = set()
        for source in (secondary or {}, primary or {}):
            for item in source.get(key) or []:
                if isinstance(item, dict):
                    marker = str(
                        (
                            item.get("category"),
                            item.get("description"),
                            item.get("type"),
                        )
                    ).lower()
                else:
                    marker = str(item).strip().lower()
                if not marker or marker in seen:
                    continue
                seen.add(marker)
                combined.append(item)
        if combined:
            merged[key] = combined

    return merged


def _normalize_package_code(value: str | None) -> str:
    return "".join(ch for ch in (value or "").upper() if ch.isalnum())


def _available_option_package_lookup(payload: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(payload, dict):
        return {}
    rows = payload.get("available_options_packages") or payload.get("options_packages") or payload.get("packages") or []
    if not isinstance(rows, list):
        return {}

    lookup: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        code = _to_str(row.get("code") or row.get("package_code") or row.get("id"))
        if not code:
            continue
        lookup[_normalize_package_code(code)] = row
    return lookup


def _package_display_name(code: str, package_row: dict[str, Any] | None) -> str:
    if not package_row:
        return code

    name = _to_str(
        package_row.get("name")
        or package_row.get("package_name")
        or package_row.get("title")
        or package_row.get("description")
    )
    if not name:
        return code

    normalized_code = _normalize_package_code(code)
    if normalized_code and normalized_code not in _normalize_package_code(name):
        return f"{name} ({code})"
    return name


def rebuild_listing_feature_merge(metadata: dict[str, Any]) -> dict[str, Any]:
    merged_feature_details: list[dict[str, str | None]] = []
    seen: set[str] = set()
    for key in ("feature_details", "high_value_feature_details", "option_details", "option_package_details"):
        for item in metadata.get(key) or []:
            if not isinstance(item, dict):
                continue
            description = _to_str(item.get("description"))
            if not description:
                continue
            marker = "|".join(
                [
                    (item.get("category") or "").strip().lower(),
                    description.strip().lower(),
                    (item.get("type") or "").strip().lower(),
                ]
            )
            if marker in seen:
                continue
            seen.add(marker)
            merged_feature_details.append(
                {
                    "category": _to_str(item.get("category")),
                    "description": description,
                    "type": _to_str(item.get("type")),
                }
            )

    metadata["feature_details"] = merged_feature_details
    metadata["features"] = [item["description"] for item in merged_feature_details if item.get("description")]
    metadata["supplemental_photo_links"] = list(
        dict.fromkeys(
            [
                *[str(item) for item in metadata.get("photo_links_cached") or [] if _to_str(item)],
                *[str(item) for item in metadata.get("photo_links") or [] if _to_str(item)],
            ]
        )
    )
    return metadata


def decode_option_packages(vin: str, metadata: dict[str, Any], client: MarketCheckClient) -> dict[str, Any]:
    raw_codes = [str(item) for item in metadata.get("option_package_codes") or metadata.get("option_packages") or [] if _to_str(item)]
    if not raw_codes:
        return metadata

    try:
        payload = client.get_available_options_packages(vin)
    except Exception:
        logger.debug("available options package decode failed vin=%s", vin, exc_info=True)
        return metadata

    lookup = _available_option_package_lookup(payload)
    if not lookup:
        return metadata

    decoded_packages: list[str] = []
    decoded_details: list[dict[str, str | None]] = []
    seen_packages: set[str] = set()
    detail_lookup = {
        _normalize_package_code(_to_str(item.get("description"))): item
        for item in (metadata.get("option_package_details") or [])
        if isinstance(item, dict) and _to_str(item.get("description"))
    }

    for code in raw_codes:
        normalized_code = _normalize_package_code(code)
        package_row = lookup.get(normalized_code)
        label = _package_display_name(code, package_row)
        marker = label.strip().lower()
        if marker and marker not in seen_packages:
            seen_packages.add(marker)
            decoded_packages.append(label)

        source_detail = detail_lookup.get(normalized_code)
        decoded_details.append(
            {
                "category": _to_str((source_detail or {}).get("category")) or "Packages",
                "description": label,
                "type": _to_str((source_detail or {}).get("type")),
            }
        )

    metadata["option_packages"] = decoded_packages
    metadata["option_package_details"] = decoded_details
    return rebuild_listing_feature_merge(metadata)


def enrichment_metadata_from_record(record: VehicleHistoryEnrichment | None) -> dict[str, Any]:
    if not record or record.status != "completed":
        return {}
    payload = dict(record.listing_metadata_json or {})
    if record.seller_comments and not payload.get("seller_comments"):
        payload["seller_comments"] = record.seller_comments
    if record.source_url and not payload.get("source_url"):
        payload["source_url"] = record.source_url
    return payload


def is_thin_listing(vehicle: Vehicle, cached_metadata: dict[str, Any] | None = None) -> bool:
    cached_metadata = cached_metadata or {}
    feature_count = len(vehicle.features_raw or [])
    feature_count = max(feature_count, len(cached_metadata.get("features") or []))
    option_packages = cached_metadata.get("option_packages") or []
    seller_comments = cached_metadata.get("seller_comments") or ""
    source_type = (vehicle.source_type or "").strip().lower()

    if source_type not in ENRICHABLE_SOURCE_TYPES:
        return False
    if feature_count < max(1, settings.marketcheck_history_enrichment_feature_min_count):
        return True
    return not option_packages and not seller_comments and source_type in {"auction", "ove"}


def _history_timestamp(entry: dict[str, Any]) -> datetime:
    epoch_seconds = _to_int(entry.get("last_seen_at") or entry.get("scraped_at") or entry.get("first_seen_at"))
    if epoch_seconds:
        try:
            return datetime.fromtimestamp(epoch_seconds, tz=UTC)
        except (OverflowError, OSError, ValueError):
            pass

    for key in (
        "last_seen_at",
        "last_seen",
        "last_seen_dt",
        "last_seen_at_date",
        "updated_at",
        "scraped_at",
        "scraped_at_date",
        "inventory_date",
        "first_seen_at",
        "first_seen",
        "first_seen_at_date",
    ):
        value = _to_str(entry.get(key))
        if not value:
            continue
        try:
            normalized = value.replace("Z", "+00:00")
            parsed = datetime.fromisoformat(normalized)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=UTC)
            return parsed.astimezone(UTC)
        except ValueError:
            continue
    return datetime.fromtimestamp(0, tz=UTC)


def _history_entries_from_payload(history_payload: Any) -> list[dict[str, Any]]:
    if isinstance(history_payload, list):
        return [row for row in history_payload if isinstance(row, dict)]
    if not isinstance(history_payload, dict):
        return []

    listings = history_payload.get("listings") or history_payload.get("history") or []
    if isinstance(history_payload.get("id"), str):
        listings = [history_payload]
    return [row for row in listings if isinstance(row, dict)]


def _source_host(url: str | None) -> str:
    text = _to_str(url)
    if not text:
        return ""
    return (urlparse(text).hostname or "").lower()


def _listing_matches_vehicle(listing: dict[str, Any] | None, *, vin: str, listing_id: str | None = None) -> bool:
    if not isinstance(listing, dict):
        return False
    listing_vin = _to_str(listing.get("vin"))
    if not listing_vin or listing_vin.upper() != vin.upper():
        return False
    if listing_id:
        returned_id = _to_str(listing.get("id") or listing.get("listing_id"))
        if returned_id and returned_id != listing_id:
            return False
    return True


def select_best_history_entry(history_payload: Any, *, preferred_source_url: str | None = None) -> dict[str, Any] | None:
    candidates = _history_entries_from_payload(history_payload)
    if not candidates:
        return None

    preferred_host = _source_host(preferred_source_url)

    def score(entry: dict[str, Any]) -> tuple[int, int, datetime]:
        listing_id = _to_str(entry.get("id") or entry.get("listing_id"))
        vdp_url = _to_str(entry.get("vdp_url") or entry.get("listing_url") or entry.get("website"))
        featureish = int(bool(entry.get("build") or entry.get("extra") or entry.get("features")))
        seller_type = (_to_str(entry.get("seller_type")) or "").lower()
        source_host = _source_host(vdp_url)
        return (
            int(bool(preferred_host) and source_host == preferred_host),
            int(seller_type == "dealer"),
            int(bool(listing_id)),
            int(bool(vdp_url)) + featureish,
            _history_timestamp(entry),
        )

    return max(candidates, key=score)


def should_refresh_enrichment(record: VehicleHistoryEnrichment | None, *, force: bool = False) -> bool:
    if force or record is None:
        return True
    now = datetime.now(UTC)
    if record.status == "completed":
        if not record.last_enriched_at:
            return True
        return record.last_enriched_at <= now - timedelta(hours=max(1, settings.marketcheck_history_enrichment_ttl_hours))
    if record.last_attempted_at is None:
        return True
    return record.last_attempted_at <= now - timedelta(hours=max(1, settings.marketcheck_history_enrichment_retry_hours))


def apply_enrichment_to_vehicle(vehicle: Vehicle, metadata: dict[str, Any], record: VehicleHistoryEnrichment) -> bool:
    changed = False

    merged_features: list[str] = []
    seen: set[str] = set()
    for source in (vehicle.features_raw or [], metadata.get("features") or []):
        for item in source:
            text = _to_str(item)
            if not text:
                continue
            key = text.lower()
            if key in seen:
                continue
            seen.add(key)
            merged_features.append(text)
    if merged_features != (vehicle.features_raw or []):
        vehicle.features_raw = merged_features
        changed = True

    normalized = dict(vehicle.features_normalized or {})
    for key in ENRICHMENT_FILL_KEYS:
        if normalized.get(key) in (None, "", [], {}):
            value = metadata.get(key)
            if value not in (None, "", [], {}):
                normalized[key] = value
                changed = True

    normalized["history_enrichment"] = {
        "provider": record.provider,
        "status": record.status,
        "source_listing_id": record.source_listing_id,
        "last_enriched_at": record.last_enriched_at.isoformat() if record.last_enriched_at else None,
        "feature_count": len(metadata.get("features") or []),
        "option_package_count": len(metadata.get("option_packages") or []),
        "seller_comments_present": bool(record.seller_comments),
    }
    vehicle.features_normalized = normalized

    if not vehicle.source_url and record.source_url:
        vehicle.source_url = record.source_url
        changed = True

    return changed


def enrich_vehicle_history(
    db: Session,
    *,
    vehicle: Vehicle,
    client: MarketCheckClient | None = None,
    force: bool = False,
) -> VehicleHistoryEnrichment:
    record = db.get(VehicleHistoryEnrichment, vehicle.vin)
    if record is None:
        record = VehicleHistoryEnrichment(vin=vehicle.vin)
        db.add(record)
        db.flush()

    source_type = (vehicle.source_type or "").strip().lower()
    if source_type not in ENRICHABLE_SOURCE_TYPES:
        record.status = "not_applicable"
        return record

    if not settings.has_marketcheck:
        record.status = "disabled"
        return record

    if not should_refresh_enrichment(record, force=force):
        return record

    client = client or build_marketcheck_client()
    now = datetime.now(UTC)
    record.attempts = int(record.attempts or 0) + 1
    record.last_attempted_at = now
    record.last_error = None

    history_payload = client.get_history(vehicle.vin)
    if not isinstance(history_payload, (dict, list)):
        record.status = "failed"
        record.last_error = "history_response_invalid"
        return record

    entry = select_best_history_entry(history_payload, preferred_source_url=vehicle.source_url)
    if not entry:
        record.status = "no_data"
        record.history_entry_json = {}
        record.listing_metadata_json = {}
        return record

    listing_id = _to_str(entry.get("id") or entry.get("listing_id"))
    listing_payload = entry
    if listing_id:
        try:
            full_listing = client.get_listing(listing_id)
            if _listing_matches_vehicle(full_listing, vin=vehicle.vin, listing_id=listing_id):
                listing_payload = full_listing
        except Exception:
            logger.debug("history listing detail fetch failed vin=%s listing_id=%s", vehicle.vin, listing_id, exc_info=True)

    metadata = extract_listing_metadata(listing_payload)
    metadata = decode_option_packages(vehicle.vin, metadata, client)
    source_comment = metadata.get("seller_comments") or metadata.get("description")
    rewritten_comment, rewrite_provider = build_virtualcarhub_seller_comment(
        vehicle=vehicle,
        source_text=source_comment,
        metadata=metadata,
    )
    metadata["seller_comments_original"] = source_comment
    if rewritten_comment:
        metadata["seller_comments"] = rewritten_comment
        metadata["seller_comment_provider"] = rewrite_provider

    if not metadata.get("features") and not metadata.get("option_packages") and not metadata.get("seller_comments"):
        record.status = "no_data"
        record.source_listing_id = listing_id
        record.source_url = _to_str(entry.get("vdp_url") or entry.get("listing_url") or entry.get("website"))
        record.history_entry_json = entry
        record.listing_payload_json = listing_payload if isinstance(listing_payload, dict) else {}
        record.listing_metadata_json = metadata
        return record

    record.status = "completed"
    record.source_listing_id = listing_id
    record.source_url = metadata.get("source_url") or _to_str(entry.get("vdp_url") or entry.get("listing_url") or entry.get("website"))
    record.seller_comments = metadata.get("seller_comments") or metadata.get("description")
    record.history_entry_json = entry
    record.listing_payload_json = listing_payload if isinstance(listing_payload, dict) else {}
    record.listing_metadata_json = metadata
    record.last_enriched_at = now

    apply_enrichment_to_vehicle(vehicle, metadata, record)
    return record


def select_thin_vehicle_candidates(db: Session, *, limit: int) -> list[Vehicle]:
    window = max(limit * 6, 50)
    vehicles = db.scalars(
        select(Vehicle)
        .where(Vehicle.available.is_(True))
        .order_by(Vehicle.updated_at.desc())
        .limit(window)
    ).all()
    out: list[Vehicle] = []
    for vehicle in vehicles:
        record = db.get(VehicleHistoryEnrichment, vehicle.vin)
        metadata = enrichment_metadata_from_record(record)
        if not is_thin_listing(vehicle, metadata):
            continue
        if not should_refresh_enrichment(record):
            continue
        out.append(vehicle)
        if len(out) >= limit:
            break
    return out


def run_history_enrichment_batch(
    db: Session,
    *,
    limit: int | None = None,
    force: bool = False,
    vins: list[str] | None = None,
) -> dict[str, Any]:
    if not settings.has_marketcheck or not settings.marketcheck_history_enrichment_enabled:
        return {"enabled": False, "processed": 0, "updated": 0, "failed": 0, "skipped": 0, "vins": []}

    client = build_marketcheck_client()
    processed = 0
    updated = 0
    failed = 0
    skipped = 0
    touched: list[str] = []

    candidates: list[Vehicle]
    if vins:
        candidates = []
        for vin in vins:
            vehicle = db.get(Vehicle, vin.upper())
            if vehicle:
                candidates.append(vehicle)
    else:
        candidates = select_thin_vehicle_candidates(
            db,
            limit=max(1, int(limit or settings.marketcheck_history_enrichment_batch_size)),
        )

    for vehicle in candidates:
        try:
            record = enrich_vehicle_history(db, vehicle=vehicle, client=client, force=force)
            db.commit()
            processed += 1
            touched.append(vehicle.vin)
            if record.status == "completed":
                updated += 1
            elif record.status in {"failed"}:
                failed += 1
            else:
                skipped += 1
        except Exception:
            db.rollback()
            processed += 1
            failed += 1
            touched.append(vehicle.vin)
            logger.warning("marketcheck_history_enrichment_failed vin=%s", vehicle.vin, exc_info=True)

    return {
        "enabled": True,
        "processed": processed,
        "updated": updated,
        "failed": failed,
        "skipped": skipped,
        "vins": touched,
    }
