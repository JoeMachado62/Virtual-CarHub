import ast
import logging
import re
from datetime import UTC, datetime, timedelta
from typing import Any

logger = logging.getLogger(__name__)

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.params import Param
from pydantic import BaseModel
from sqlalchemy import Integer, and_, asc, case, desc, false, func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import get_optional_user, is_admin_user, require_service_token
from app.core.config import settings
from app.core.constants import FundingState, ImageTier, InventorySourceType
from app.core.responses import ok
from app.db.session import get_db
from app.integrations.marketcheck_client import MarketCheckClient
from app.integrations.nhtsa_client import NHTSAClient, categorize_decode
from app.models.entities import (
    Deal,
    GarageItem,
    HotDeal,
    OveVehicleDetail,
    User,
    Vehicle,
    VehicleHistoryEnrichment,
    VehicleImageAsset,
    VehicleMarketComparisonCache,
    VehicleTaxonomyCache,
)
from app.services.marketcheck_history_enrichment_service import (
    enrich_vehicle_history,
    enrichment_metadata_from_record,
    is_thin_listing,
    merge_listing_metadata,
    run_history_enrichment_batch,
    select_best_history_entry,
)
from app.services.seller_comment_service import (
    build_virtualcarhub_seller_comment,
    cache_vehicle_seller_comment,
    get_cached_vehicle_seller_comment,
)
from app.services.hot_deal_service import get_active_hot_deals, serialize_hot_deal
from app.services.image_pipeline_service import resolve_vehicle_card_media, resolve_vehicle_display_context
from app.services.inventory_taxonomy_service import (
    MIN_TAXONOMY_YEAR,
    get_inventory_taxonomy_facets,
    sync_marketcheck_taxonomy_cache,
)
from app.services.payment_estimate_service import (
    DEFAULT_CREDIT_TIER_ID,
    DEFAULT_LOAN_TERM_MONTHS,
    build_payment_estimate,
)
from app.services.photo_access_service import (
    can_view_protected_vehicle_photos,
    protected_photo_access_message,
)
from app.services.inventory_service import SOURCE_PRIORITY, ingest_marketcheck_inventory, seed_inventory
from app.services.zip_radius_service import normalize_zip_code, zip_codes_within_radius

router = APIRouter()


def _split_csv(value: str | None) -> list[str]:
    """Split a comma-separated query param into a lowercased list."""
    if not value:
        return []
    return [v.strip().lower() for v in value.split(",") if v.strip()]


def _model_in(values: list[str]):
    model_expr = func.lower(func.coalesce(Vehicle.model, ""))
    return model_expr.in_(values)


def _model_prefixes(prefixes: list[str]):
    model_expr = func.lower(func.coalesce(Vehicle.model, ""))
    return or_(*[model_expr.like(f"{prefix}%") for prefix in prefixes])


def _inferred_body_type_expr():
    """Infer broad body type for thin auction rows that do not carry one."""
    make_expr = func.lower(func.coalesce(Vehicle.make, ""))
    body_expr = func.lower(func.nullif(func.coalesce(Vehicle.body_type, ""), ""))

    suv_expr = or_(
        and_(make_expr == "acura", _model_in(["mdx", "rdx", "zdx"])),
        and_(make_expr == "audi", _model_prefixes(["q3", "q4", "q5", "q7", "q8", "sq5", "sq7", "sq8", "rs q8"])),
        and_(make_expr == "bmw", _model_prefixes(["x1", "x2", "x3", "x4", "x5", "x6", "x7", "xm", "ix"])),
        and_(make_expr == "genesis", _model_prefixes(["gv60", "gv70", "gv80"])),
        and_(make_expr == "infiniti", _model_prefixes(["qx30", "qx50", "qx55", "qx60", "qx70", "qx80"])),
        and_(make_expr == "lincoln", _model_in(["corsair", "nautilus", "aviator", "navigator", "navigator l"])),
        and_(make_expr == "mercedes-benz", _model_prefixes(["gla", "glb", "glc", "gle", "gls", "g-class", "eqb"])),
        and_(make_expr == "volvo", _model_prefixes(["xc40", "xc60", "xc90", "ex30", "ex90", "c40"])),
        and_(make_expr == "cadillac", _model_prefixes(["xt4", "xt5", "xt6", "escalade"])),
        and_(make_expr == "chevrolet", _model_in(["blazer", "equinox", "suburban", "tahoe", "trailblazer", "traverse"])),
        and_(make_expr == "ford", _model_in(["bronco", "bronco sport", "edge", "escape", "expedition", "explorer", "mustang mach-e"])),
        and_(make_expr == "gmc", _model_in(["acadia", "terrain", "yukon", "yukon xl"])),
        and_(make_expr == "honda", _model_in(["cr-v", "hr-v", "passport", "pilot", "prologue"])),
        and_(make_expr == "hyundai", _model_in(["ioniq 5", "kona", "palisade", "santa fe", "tucson", "venue"])),
        and_(make_expr == "jeep", _model_prefixes(["cherokee", "compass", "grand cherokee", "grand wagoneer", "renegade", "wagoneer", "wrangler"])),
        and_(make_expr == "kia", _model_in(["ev6", "ev9", "niro", "seltos", "sorento", "soul", "sportage", "telluride"])),
        and_(make_expr == "land rover", _model_prefixes(["defender", "discovery", "range rover"])),
        and_(make_expr == "lexus", _model_prefixes(["gx", "lx", "nx", "rx", "rz", "tx", "ux"])),
        and_(make_expr == "mazda", _model_prefixes(["cx-3", "cx-30", "cx-5", "cx-50", "cx-70", "cx-9", "cx-90"])),
        and_(make_expr == "nissan", _model_in(["ariya", "armada", "kicks", "murano", "pathfinder", "rogue"])),
        and_(make_expr == "porsche", _model_in(["cayenne", "macan"])),
        and_(make_expr == "subaru", _model_in(["ascent", "crosstrek", "forester", "outback", "solterra"])),
        and_(make_expr == "tesla", _model_in(["model x", "model y"])),
        and_(make_expr == "toyota", _model_in(["4runner", "bz4x", "c-hr", "corolla cross", "grand highlander", "highlander", "land cruiser", "rav4", "sequoia", "venza"])),
        and_(make_expr == "volkswagen", _model_in(["atlas", "atlas cross sport", "id.4", "taos", "tiguan"])),
    )
    truck_expr = or_(
        and_(make_expr == "chevrolet", _model_prefixes(["colorado", "silverado"])),
        and_(make_expr == "ford", _model_prefixes(["f-150", "f-250", "f-350", "maverick", "ranger"])),
        and_(make_expr == "gmc", _model_prefixes(["canyon", "sierra"])),
        and_(make_expr == "honda", _model_in(["ridgeline"])),
        and_(make_expr == "jeep", _model_in(["gladiator"])),
        and_(make_expr == "nissan", _model_in(["frontier", "titan"])),
        and_(make_expr == "ram", _model_prefixes(["1500", "2500", "3500"])),
        and_(make_expr == "rivian", _model_in(["r1t"])),
        and_(make_expr == "toyota", _model_in(["tacoma", "tundra"])),
    )
    minivan_expr = or_(
        and_(make_expr == "chrysler", _model_in(["pacifica", "voyager"])),
        and_(make_expr == "honda", _model_in(["odyssey"])),
        and_(make_expr == "kia", _model_in(["carnival"])),
        and_(make_expr == "toyota", _model_in(["sienna"])),
    )

    return func.coalesce(
        body_expr,
        case(
            (suv_expr, "suv"),
            (truck_expr, "truck"),
            (minivan_expr, "minivan"),
            else_=None,
        ),
    )


def _split_make_model_pairs(value: str | None) -> list[tuple[str, str]]:
    if not value or not isinstance(value, str):
        return []
    pairs: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for raw in value.split(","):
        text = raw.strip()
        if not text:
            continue
        if "|||" in text:
            make, model = text.split("|||", 1)
        elif "|" in text:
            make, model = text.split("|", 1)
        else:
            continue
        pair = (make.strip().lower(), model.strip().lower())
        if not pair[0] or not pair[1] or pair in seen:
            continue
        seen.add(pair)
        pairs.append(pair)
    return pairs


def _apply_make_model_filters(stmt, make: str | None, model: str | None, make_model_pairs: str | None = None):
    pairs = _split_make_model_pairs(make_model_pairs)
    if pairs:
        return stmt.where(
            or_(
                *[
                    and_(
                        func.lower(Vehicle.make) == pair_make,
                        func.lower(Vehicle.model) == pair_model,
                    )
                    for pair_make, pair_model in pairs
                ]
            )
        )

    makes = _split_csv(make)
    if makes:
        stmt = stmt.where(func.lower(Vehicle.make).in_(makes))
    models = _split_csv(model)
    if models:
        stmt = stmt.where(func.lower(Vehicle.model).in_(models))
    return stmt


FACET_FIELDS = [
    "make",
    "model",
    "trim",
    "body_type",
    "state",
    "city",
    "exterior_color",
    "interior_color",
    "drivetrain",
    "fuel_type",
    "transmission",
    "inventory_type",
]


SLUG_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")
PUBLIC_AUCTION_SOURCE = "auction"
PUBLIC_WHOLESALE_SOURCE = "wholesale"
PUBLIC_RETAIL_SOURCE = "retail"
VCH_MARGIN = 1500.0
AUCTION_BUY_FEE_UNDER_50K = 1000.0
AUCTION_BUY_FEE_OVER_50K = 1300.0
DETAIL_SHOP_FEE = 150.0
MARKETING_FEE = 599.0
AGED_INVENTORY_MIN_DOM = 60


def _marketcheck_client() -> MarketCheckClient:
    return MarketCheckClient(
        api_key=settings.marketcheck_api_key,
        api_secret=settings.marketcheck_api_secret,

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


def _to_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_feature_list(values: Any) -> list[str]:
    return [item["description"] for item in _normalize_feature_details(values)]


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


def _parse_facet_buckets(values: Any) -> list[dict[str, Any]]:
    if not isinstance(values, list):
        return []
    buckets: list[dict[str, Any]] = []
    for raw in values:
        if isinstance(raw, dict):
            item = _to_str(raw.get("item"))
            if not item:
                continue
            buckets.append({"item": item, "count": int(raw.get("count") or 0)})
        else:
            item = _to_str(raw)
            if item:
                buckets.append({"item": item, "count": 0})
    return buckets


def _to_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    normalized = value if value.tzinfo else value.replace(tzinfo=UTC)
    return normalized.astimezone(UTC).isoformat()


def _is_auction_source(source_type: str | None) -> bool:
    normalized = (source_type or "").strip().lower()
    return normalized in {
        InventorySourceType.AUCTION.value,
        InventorySourceType.OVE.value,
    }


def _is_wholesale_source(source_type: str | None) -> bool:
    normalized = (source_type or "").strip().lower()
    return normalized in {
        InventorySourceType.MARKETCHECK.value,
        InventorySourceType.DEALER_WHOLESALE.value,
    }


def _public_source_value(source_type: str | None) -> str:
    if _is_auction_source(source_type):
        return PUBLIC_AUCTION_SOURCE
    if _is_wholesale_source(source_type):
        return PUBLIC_WHOLESALE_SOURCE
    return (source_type or "")


def _public_source_label(source_type: str | None) -> str:
    if _is_auction_source(source_type):
        return "Wholesale Direct"
    if _is_wholesale_source(source_type):
        return "Surplus Inventory"
    normalized = (source_type or "").strip()
    if not normalized:
        return "Inventory"
    if normalized.lower() == InventorySourceType.DEALER_PARTNER.value:
        return "Partner Network"
    return normalized.replace("_", " ").title()


def _auction_buy_fee(base_price: float | None) -> float:
    amount = _to_float(base_price) or 0.0
    return AUCTION_BUY_FEE_UNDER_50K if amount <= 50000 else AUCTION_BUY_FEE_OVER_50K


def _pricing_breakdown(base_price: float | None) -> dict[str, float | None]:
    source_price = _to_float(base_price)
    if source_price is None:
        return {
            "source_price": None,
            "buy_fee": None,
            "detail_shop_fee": round(DETAIL_SHOP_FEE, 2),
            "margin": VCH_MARGIN,
            "marketing_fee": round(MARKETING_FEE, 2),
            "advertised_price": None,
        }
    buy_fee = _auction_buy_fee(source_price)
    return {
        "source_price": round(source_price, 2),
        "buy_fee": round(buy_fee, 2),
        "detail_shop_fee": round(DETAIL_SHOP_FEE, 2),
        "margin": round(VCH_MARGIN, 2),
        "marketing_fee": round(MARKETING_FEE, 2),
        "advertised_price": round(source_price + buy_fee + DETAIL_SHOP_FEE + VCH_MARGIN + MARKETING_FEE, 2),
    }


def _advertised_price_expr():
    return case(
        (
            Vehicle.price_asking <= 50000,
            Vehicle.price_asking + AUCTION_BUY_FEE_UNDER_50K + DETAIL_SHOP_FEE + VCH_MARGIN + MARKETING_FEE,
        ),
        else_=Vehicle.price_asking + AUCTION_BUY_FEE_OVER_50K + DETAIL_SHOP_FEE + VCH_MARGIN + MARKETING_FEE,
    )


def _aged_inventory_dom_expr():
    return Vehicle.features_normalized["days_on_market"].as_string().cast(Integer)


def _model_filter_expr(model: str):
    """Match model exactly or as a prefix so 'Sierra' finds 'Sierra 1500' etc."""
    model_lower = model.lower()
    return or_(
        func.lower(Vehicle.model) == model_lower,
        func.lower(Vehicle.model).like(model_lower + " %"),
    )


def _apply_source_type_filter(stmt, source_type: str | None):
    if not source_type:
        return stmt
    normalized = source_type.strip().lower()
    if normalized == PUBLIC_AUCTION_SOURCE:
        return stmt.where(
            func.lower(Vehicle.source_type).in_(
                [InventorySourceType.AUCTION.value, InventorySourceType.OVE.value]
            )
        )
    if normalized == PUBLIC_WHOLESALE_SOURCE:
        return stmt.where(
            func.lower(Vehicle.source_type).in_(
                [InventorySourceType.MARKETCHECK.value, InventorySourceType.DEALER_WHOLESALE.value]
            )
        )
    if normalized == InventorySourceType.OVE.value:
        return stmt.where(func.lower(Vehicle.source_type) == InventorySourceType.OVE.value)
    return stmt.where(func.lower(Vehicle.source_type) == normalized)


def _should_apply_default_aged_inventory_min(source_type: str | None) -> bool:
    normalized = (source_type or "").strip().lower()
    return not normalized


def _zip_radius_values(zip_code: str | None, radius: int | None) -> tuple[str, ...] | None:
    normalized = normalize_zip_code(zip_code)
    if not normalized:
        return None
    if radius is None:
        return (normalized,)
    return zip_codes_within_radius(normalized, radius)


def _apply_zip_radius_filter(stmt, zip_code: str | None, radius: int | None):
    zip_values = _zip_radius_values(zip_code, radius)
    if zip_values is None:
        return stmt
    if not zip_values:
        return stmt.where(false())
    # Include auction/OVE vehicles even when their location_zip is NULL,
    # since auction vehicles are nationwide and can be shipped anywhere.
    auction_expr = func.lower(Vehicle.source_type).in_(
        [InventorySourceType.AUCTION.value, InventorySourceType.OVE.value]
    )
    return stmt.where(
        or_(
            Vehicle.location_zip.in_(zip_values),
            auction_expr & Vehicle.location_zip.is_(None),
        )
    )


def _normalized_pick(normalized: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = normalized.get(key)
        if value not in (None, "", []):
            return value
    return None


def _compute_deal_rating(price_asking: float | None, mmr: Any) -> dict[str, Any] | None:
    """Return deal-quality label based on price_asking / MMR ratio."""
    if not mmr or not price_asking:
        return None
    try:
        mmr_f = float(mmr)
    except (TypeError, ValueError):
        return None
    if mmr_f <= 0:
        return None
    ratio = round(price_asking / mmr_f, 2)
    if ratio >= 1.50:
        label, color = "High", "red"
    elif ratio >= 1.25:
        label, color = "Fair", "orange"
    elif ratio >= 1.10:
        label, color = "Good", "yellow"
    elif ratio >= 0.96:
        label, color = "Great", "green"
    else:
        label, color = "Excellent", "green"
    return {"ratio": ratio, "label": label, "color": color}


def _compute_badges(
    year: int | None,
    odometer: int | None,
    price_asking: float | None,
    mmr: Any,
) -> list[dict[str, str]]:
    """Build a list of qualifying badge dicts for a vehicle."""
    current_year = datetime.now(UTC).year
    badges: list[dict[str, str]] = []

    # Deal quality badge (MMR-based)
    deal = _compute_deal_rating(price_asking, mmr)
    if deal:
        badges.append({"type": "deal_quality", "label": deal["label"], "color": deal["color"], "ratio": str(deal["ratio"])})

    if year is not None and odometer is not None:
        age = current_year - year
        # Factory Warranty badge
        if age < 3 and odometer < 36_000:
            badges.append({"type": "factory_warranty", "label": "Factory Warranty*", "color": "blue"})
        # CPO eligibility badge
        if age < 5 and odometer < 80_000:
            badges.append({"type": "cpo_eligible", "label": "Ask About CPO", "color": "teal"})

    return badges


def _parse_iso8601(value: str | None) -> datetime | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    if not text:
        return None
    normalized = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _normalize_slug_part(value: Any) -> str:
    text = _to_str(value)
    if not text:
        return ""
    return SLUG_NON_ALNUM_RE.sub("-", text.lower()).strip("-")


def _resolve_direct_param(value: Any) -> Any:
    return value.default if isinstance(value, Param) else value


def _friendly_live_sync_error(_: Exception) -> str:
    return "Live wholesale sync is temporarily unavailable. Showing saved inventory results."


def _extract_cr_url(ove_detail) -> str | None:
    if not ove_detail or not ove_detail.condition_report_json:
        return None
    metadata = ove_detail.condition_report_json.get("metadata") or {}
    report_link = metadata.get("report_link") or {}
    return report_link.get("href") or None


def _build_vehicle_title(vehicle: Vehicle) -> str:
    parts = [str(vehicle.year), vehicle.make, vehicle.model]
    trim = _to_str(vehicle.trim)
    if trim:
        parts.append(trim)
    return " ".join([part for part in parts if part]).strip()


def _build_vehicle_slug(vehicle: Vehicle) -> str:
    # Human-readable URL slug used by the WordPress export and the
    # /cars/<id>/<slug> canonical URL. We intentionally swap the VIN for
    # the public_slug so the last six production-sequence digits never
    # leak into public page URLs or search-indexed metadata.
    identifier = (vehicle.public_slug or vehicle.vin or "").lower()
    parts = [
        _normalize_slug_part(vehicle.year),
        _normalize_slug_part(vehicle.make),
        _normalize_slug_part(vehicle.model),
        _normalize_slug_part(vehicle.trim),
        _normalize_slug_part(identifier),
    ]
    filtered = [part for part in parts if part]
    return "-".join(filtered) or identifier


def _build_vdp_links(vehicle_or_vin) -> tuple[str, str]:
    # Accept either a Vehicle row or a bare VIN so legacy call sites keep
    # working; always emit the public slug if available.
    if hasattr(vehicle_or_vin, "public_slug"):
        identifier = vehicle_or_vin.public_slug or vehicle_or_vin.vin
    else:
        identifier = vehicle_or_vin
    path = f"/vinventory/{identifier}"
    base = settings.public_web_base_url.rstrip("/")
    return path, f"{base}{path}"


def _dedupe_strings(values: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = _to_str(value)
        if not text:
            continue
        key = text.strip()
        if key in seen:
            continue
        seen.add(key)
        out.append(key)
    return out



def _extract_search_average(payload: Any, field: str) -> float | None:
    if not isinstance(payload, dict):
        return None

    candidates: list[Any] = []
    stats = payload.get("stats")
    if isinstance(stats, dict):
        field_stats = stats.get(field)
        if isinstance(field_stats, dict):
            candidates.extend(
                [
                    field_stats.get("mean"),
                    field_stats.get("avg"),
                    field_stats.get("average"),
                    field_stats.get("median"),
                ]
            )
        candidates.extend(
            [
                stats.get(f"{field}_mean"),
                stats.get(f"{field}_avg"),
                stats.get(f"{field}_average"),
                stats.get(f"avg_{field}"),
            ]
        )

    for candidate in candidates:
        parsed = _to_float(candidate)
        if parsed is not None and parsed > 0:
            return round(parsed, 2)
    return None


def _extract_listing_miles(row: dict[str, Any]) -> int | None:
    return _to_int(
        row.get("miles")
        or row.get("mileage")
        or row.get("odometer")
        or row.get("miles_unformatted")
    )


def _market_comparison_point_from_listing(
    row: dict[str, Any],
    *,
    vch_vehicle: Vehicle | None = None,
) -> dict[str, Any] | None:
    if vch_vehicle:
        if vch_vehicle.odometer is None or not vch_vehicle.price_asking:
            return None
        return {
            "vin": vch_vehicle.vin,
            "label": f"{vch_vehicle.year} {vch_vehicle.make} {vch_vehicle.model}{(' ' + vch_vehicle.trim) if vch_vehicle.trim else ''}",
            "price": _pricing_breakdown(vch_vehicle.price_asking)["advertised_price"],
            "miles": vch_vehicle.odometer,
            "source": "vch",
            "is_vch_listing": True,
            "href": f"/vinventory/{vch_vehicle.public_slug or vch_vehicle.vin}",
        }

    price = _to_float(row.get("price") or row.get("price_asking") or row.get("asking_price"))
    miles = _extract_listing_miles(row)
    vin = _to_str(row.get("vin"))

    if price is None or price <= 0 or miles is None or miles < 0:
        return None

    label_parts = [
        _to_str(row.get("year")),
        _to_str(row.get("make")),
        _to_str(row.get("model")),
        _to_str(row.get("trim")),
    ]

    point = {
        "vin": vin,
        "label": " ".join(part for part in label_parts if part) or "Comparable vehicle",
        "price": round(price, 2),
        "miles": miles,
        "source": "vch" if vch_vehicle else "marketcheck",
        "is_vch_listing": bool(vch_vehicle),
        "href": None,
    }

    return point


def _local_comparable_vehicles(db: Session, vehicle: Vehicle, *, limit: int = 20) -> list[Vehicle]:
    stmt = (
        select(Vehicle)
        .where(
            Vehicle.vin != vehicle.vin,
            Vehicle.available == True,  # noqa: E712
            Vehicle.odometer.is_not(None),
            Vehicle.price_asking > 0,
            func.lower(Vehicle.make) == (vehicle.make or "").lower(),
            func.lower(Vehicle.model) == (vehicle.model or "").lower(),
            Vehicle.year >= (vehicle.year or 2020) - 2,
            Vehicle.year <= (vehicle.year or 2020) + 2,
        )
        .order_by(
            case((Vehicle.year == vehicle.year, 0), else_=1),
            case((func.lower(func.coalesce(Vehicle.trim, "")) == (vehicle.trim or "").lower(), 0), else_=1),
            Vehicle.updated_at.desc(),
        )
        .limit(limit)
    )
    if vehicle.trim:
        trim_text = vehicle.trim.lower()
        exact_trim_stmt = stmt.where(func.lower(func.coalesce(Vehicle.trim, "")) == trim_text).limit(limit)
        exact_rows = list(db.scalars(exact_trim_stmt).all())
        if len(exact_rows) >= min(4, limit):
            return exact_rows
    return list(db.scalars(stmt).all())


def _build_market_comparison_payload(db: Session, vehicle: Vehicle) -> dict[str, Any]:
    local_rows = _local_comparable_vehicles(db, vehicle, limit=20)
    vch_by_vin = {row.vin: row for row in local_rows}

    points: list[dict[str, Any]] = []
    seen_vins: set[str] = set()
    for row in local_rows:
        point = _market_comparison_point_from_listing({}, vch_vehicle=row)
        if not point or point.get("miles") is None:
            continue
        points.append(point)
        seen_vins.add(row.vin)

    marketcheck_payload: dict[str, Any] | None = None
    mds_payload: dict[str, Any] | None = None
    national_price: float | None = None
    national_miles: float | None = None

    if settings.has_marketcheck:
        client = _marketcheck_client()
        try:
            marketcheck_payload = client.search_inventory(
                {
                    "vins": vehicle.vin,
                    "match": "year,make,model,trim",
                    "stats": "price,miles",
                    "rows": 20,
                    "start": 0,
                    "car_type": "used",
                    "exclude_certified": "true",
                }
            )
            for listing in marketcheck_payload.get("listings", []) if isinstance(marketcheck_payload, dict) else []:
                if not isinstance(listing, dict):
                    continue
                listing_vin = (_to_str(listing.get("vin")) or "").upper()
                if listing_vin == vehicle.vin or listing_vin in seen_vins:
                    continue
                vch_match = vch_by_vin.get(listing_vin) or (db.get(Vehicle, listing_vin) if listing_vin else None)
                point = _market_comparison_point_from_listing(listing, vch_vehicle=vch_match)
                if not point:
                    continue
                points.append(point)
                if listing_vin:
                    seen_vins.add(listing_vin)
                if len(points) >= 20:
                    break
            national_price = _extract_search_average(marketcheck_payload, "price")
            national_miles = _extract_search_average(marketcheck_payload, "miles")
        except Exception:
            logger.debug("market comparison comparable search failed vin=%s", vehicle.vin, exc_info=True)

        try:
            mds_payload = client.get_market_days_supply(
                {
                    "vin": vehicle.vin,
                    "exact": "true",
                    "debug": "true",
                    "car_type": "used",
                    "exclude_certified": "true",
                }
            )
        except Exception:
            logger.debug("market comparison mds failed vin=%s", vehicle.vin, exc_info=True)

    if national_price is None:
        prices = [point["price"] for point in points if _to_float(point.get("price"))]
        national_price = round(sum(prices) / len(prices), 2) if prices else None
    if national_miles is None:
        miles_values = [point["miles"] for point in points if _to_int(point.get("miles")) is not None]
        national_miles = round(sum(miles_values) / len(miles_values), 0) if miles_values else vehicle.odometer

    # Add $500 buffer to comparable average for Avg. Market Price
    if national_price is not None:
        national_price = round(national_price + 500, 2)

    pricing = _pricing_breakdown(vehicle.price_asking)
    active_units = _to_int((mds_payload or {}).get("total_active_cars_for_ymmt")) if isinstance(mds_payload, dict) else None
    sold_units = _to_int((mds_payload or {}).get("total_cars_sold_in_last_45_days")) if isinstance(mds_payload, dict) else None
    market_days_supply = _to_int((mds_payload or {}).get("mds")) if isinstance(mds_payload, dict) else None

    if active_units is None:
        active_units = len(points) + 1

    return {
        "vin": vehicle.vin,
        "generated_at": _to_iso(datetime.now(UTC)),
        "this_vehicle": {
            "vin": vehicle.vin,
            "label": f"{vehicle.year} {vehicle.make} {vehicle.model}{(' ' + vehicle.trim) if vehicle.trim else ''}",
            "price": pricing["advertised_price"],
            "miles": vehicle.odometer,
            "href": f"/vinventory/{vehicle.public_slug or vehicle.vin}",
        },
        "comparables": points[:20],
        "national_average": {
            "label": "Avg. Market Price",
            "price": national_price,
            "miles": vehicle.odometer or national_miles,
            "source": "marketcheck_search" if marketcheck_payload else "vch_comparables",
        },
        "metrics": {
            "available_units": active_units,
            "market_days_supply": market_days_supply,
            "sold_units_45_days": sold_units,
        },
        "sources": {
            "local_comparable_count": len(local_rows),
            "marketcheck_enabled": bool(settings.has_marketcheck),
            "marketcheck_comparable_count": len(marketcheck_payload.get("listings", [])) if isinstance(marketcheck_payload, dict) else 0,
            "mds_available": bool(mds_payload),
            "price_prediction_available": False,
        },
    }


def _market_comparison_cache_ttl() -> timedelta:
    ttl_hours = max(0, settings.market_comparison_cache_ttl_hours)
    return timedelta(hours=ttl_hours)


def _get_cached_market_comparison_payload(db: Session, vehicle: Vehicle) -> dict[str, Any] | None:
    if _market_comparison_cache_ttl().total_seconds() <= 0:
        return None

    cache = db.scalar(
        select(VehicleMarketComparisonCache).where(
            VehicleMarketComparisonCache.vin == vehicle.vin,
            VehicleMarketComparisonCache.expires_at > datetime.now(UTC),
        )
    )
    if cache and isinstance(cache.payload_json, dict):
        return cache.payload_json
    return None


def _write_market_comparison_cache(db: Session, vehicle: Vehicle, payload: dict[str, Any]) -> None:
    ttl = _market_comparison_cache_ttl()
    if ttl.total_seconds() <= 0:
        return

    now = datetime.now(UTC)
    cache = db.get(VehicleMarketComparisonCache, vehicle.vin)
    if cache is None:
        cache = VehicleMarketComparisonCache(
            vin=vehicle.vin,
            generated_at=now,
            expires_at=now + ttl,
        )
        db.add(cache)
    cache.payload_json = payload
    cache.generated_at = now
    cache.expires_at = now + ttl
    try:
        db.commit()
    except Exception:
        db.rollback()
        logger.debug("market comparison cache write failed vin=%s", vehicle.vin, exc_info=True)


def _build_marketcheck_search_params(
    *,
    q: str | None,
    make: str | None,
    model: str | None,
    trim: str | None,
    body_type: str | None,
    state: str | None,
    min_price: float | None,
    max_price: float | None,
    min_year: int | None,
    max_year: int | None,
    has_images: bool | None,
    exterior_color: str | None,
    interior_color: str | None,
    drivetrain: str | None,
    fuel_type: str | None,
    transmission: str | None,
    inventory_type: str | None,
    certified: bool | None,
    single_owner: bool | None,
    clean_title: bool | None,
    min_dom: int | None,
    max_dom: int | None,
    zip_code: str | None,
    radius: int | None,
) -> dict[str, Any]:
    search_text = (q or "").strip()
    inferred_make = None
    inferred_model = None
    inferred_trim = None
    if search_text and len(search_text) != 17 and not any([make, model, trim]):
        parts = [part for part in search_text.replace("/", " ").split() if part]
        if len(parts) == 1:
            inferred_make = parts[0]
        elif len(parts) >= 2:
            inferred_make = parts[0]
            inferred_model = parts[1]
            if len(parts) >= 3:
                inferred_trim = " ".join(parts[2:])

    params: dict[str, Any] = {
        "make": make or inferred_make,
        "model": model or inferred_model,
        "trim": trim or inferred_trim,
        "body_type": body_type,
        "car_type": body_type,
        "state": state.upper() if state else None,
        "exterior_color": exterior_color,
        "interior_color": interior_color,
        "drivetrain": drivetrain,
        "fuel_type": fuel_type,
        "transmission": transmission,
        "inventory_type": inventory_type,
        "vin": search_text.upper() if search_text and len(search_text) == 17 else None,
        "has_photo": has_images if has_images is True else None,
        "certified": str(certified).lower() if certified is not None else None,
        "carfax_1_owner": str(single_owner).lower() if single_owner is not None else None,
        "carfax_clean_title": str(clean_title).lower() if clean_title is not None else None,
        "zip": zip_code,
        "radius": radius,
    }

    if min_price is not None and max_price is not None:
        params["price_range"] = f"{int(min_price)}-{int(max_price)}"
    if min_year is not None and max_year is not None:
        if min_year == max_year:
            params["year"] = min_year
        else:
            params["year_range"] = f"{min_year}-{max_year}"
    if min_dom is not None or max_dom is not None:
        low = min_dom if min_dom is not None else 0
        high = max_dom if max_dom is not None else 9999
        params["dom_range"] = f"{low}-{high}"
    return {k: v for k, v in params.items() if v not in (None, "")}


def _extract_listing_metadata(listing: dict[str, Any] | None) -> dict[str, Any]:
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

    photo_links = [str(item) for item in (media.get("photo_links") or []) if _to_str(item)]
    photo_links_cached = [str(item) for item in (media.get("photo_links_cached") or []) if _to_str(item)]

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


def _fetch_marketcheck_listing_by_vehicle(client: MarketCheckClient, vehicle: Vehicle) -> dict[str, Any] | None:
    listing: dict[str, Any] | None = None

    if vehicle.listing_id:
        try:
            payload = client.get_listing(vehicle.listing_id)
            if isinstance(payload, dict) and payload.get("vin"):
                listing = payload
        except Exception:
            listing = None

    if not listing:
        try:
            payload = client.search_inventory({"rows": 1, "start": 0, "vin": vehicle.vin})
            rows = payload.get("listings", []) if isinstance(payload, dict) else []
            if rows and isinstance(rows[0], dict):
                listing = rows[0]
        except Exception:
            listing = None

    return listing


def _try_marketcheck_history_enrichment(vehicle: Vehicle) -> dict[str, Any]:
    """For auction/OVE vehicles, look up MarketCheck history to find the last
    retail listing, then pull build data, factory colors, and options."""
    try:
        client = _marketcheck_client()
        history = client.get_history(vehicle.vin)
        if not isinstance(history, (dict, list)):
            return {}

        if isinstance(history, list):
            listings = [entry for entry in history if isinstance(entry, dict)]
        else:
            listings = history.get("listings") or history.get("history") or []
            if isinstance(history.get("id"), str):
                # Single-object response — the history endpoint itself returned a listing
                listings = [history]
        if not listings:
            return {}

        best = select_best_history_entry(listings, preferred_source_url=vehicle.source_url)
        if not best:
            best = listings[0] if isinstance(listings[0], dict) else {}

        # If we got a listing_id but minimal data, fetch the full listing
        listing_id = best.get("id") or best.get("listing_id")
        if listing_id and not best.get("build"):
            try:
                full = client.get_listing(str(listing_id))
                if isinstance(full, dict) and (full.get("vin") or "").upper() == vehicle.vin.upper():
                    best = full
            except Exception:
                pass

        metadata = _extract_listing_metadata(best)
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
        return metadata
    except Exception:
        logger.debug("MarketCheck history enrichment failed for vin=%s", vehicle.vin, exc_info=True)
        return {}


def _local_facets(
    db: Session,
    *,
    q: str | None,
    make: str | None,
    model: str | None,
    make_model_pairs: str | None,
    trim: str | None,
    state: str | None,
    body_type: str | None,
    inventory_type: str | None,
    min_price: float | None,
    max_price: float | None,
    min_year: int | None,
    max_year: int | None,
    min_miles: int | None,
    max_miles: int | None,
    exterior_color: str | None,
    interior_color: str | None,
    zip_code: str | None,
    radius: int | None,
    has_images: bool | None,
    source_type: str | None,
) -> dict[str, Any]:
    stmt = select(Vehicle).where(Vehicle.available.is_(True))
    advertised_price = _advertised_price_expr()
    if q:
        clean_q = q.strip()
        if len(clean_q) == 17 and clean_q.isalnum():
            stmt = stmt.where(func.upper(Vehicle.vin) == clean_q.upper())
        else:
            text = f"%{clean_q.lower()}%"
            stmt = stmt.where(
                or_(
                    func.lower(Vehicle.vin).like(text),
                    func.lower(Vehicle.make).like(text),
                    func.lower(Vehicle.model).like(text),
                    func.lower(func.coalesce(Vehicle.trim, "")).like(text),
                )
            )
    stmt = _apply_make_model_filters(stmt, make, model, make_model_pairs)
    trims = _split_csv(trim)
    if trims:
        stmt = stmt.where(func.lower(func.coalesce(Vehicle.trim, "")).in_(trims))
    if state:
        stmt = stmt.where(func.lower(Vehicle.location_state) == state.lower())
    body_types = _split_csv(body_type)
    if body_types:
        stmt = stmt.where(_inferred_body_type_expr().in_(body_types))
    stmt = _apply_source_type_filter(stmt, source_type)
    if min_price is not None:
        stmt = stmt.where(advertised_price >= min_price)
    if max_price is not None:
        stmt = stmt.where(advertised_price <= max_price)
    if min_year is not None:
        stmt = stmt.where(Vehicle.year >= min_year)
    if max_year is not None:
        stmt = stmt.where(Vehicle.year <= max_year)
    if min_miles is not None:
        stmt = stmt.where(Vehicle.odometer >= min_miles)
    if max_miles is not None:
        stmt = stmt.where(Vehicle.odometer <= max_miles)
    stmt = _apply_zip_radius_filter(stmt, zip_code, radius)

    rows = db.scalars(stmt).all()

    facets: dict[str, dict[str, int]] = {name: {} for name in FACET_FIELDS}
    for row in rows:
        def add(name: str, value: str | None) -> None:
            text = _to_str(value)
            if not text:
                return
            facets[name][text] = facets[name].get(text, 0) + 1

        normalized = row.features_normalized or {}
        if inventory_type and (_to_str(normalized.get("inventory_type", "")) or "").lower() != inventory_type.lower():
            continue
        if has_images is True and not row.images:
            continue
        if exterior_color:
            ext_parts = _split_csv(exterior_color)
            ext_value = (_to_str(normalized.get("exterior_color")) or "").lower()
            if ext_parts and not any(part in ext_value for part in ext_parts):
                continue
        if interior_color:
            int_parts = _split_csv(interior_color)
            int_value = (_to_str(normalized.get("interior_color")) or "").lower()
            if int_parts and not any(part in int_value for part in int_parts):
                continue

        add("make", row.make)
        add("model", row.model)
        add("trim", row.trim)
        add("body_type", row.body_type)
        add("state", row.location_state)
        add("city", normalized.get("city"))
        add("exterior_color", normalized.get("exterior_color") or None)
        add("interior_color", normalized.get("interior_color") or None)
        add("drivetrain", normalized.get("drivetrain") or row.drivetrain)
        add("fuel_type", normalized.get("fuel_type") or None)
        add("transmission", normalized.get("transmission") or None)
        add("inventory_type", normalized.get("inventory_type"))

    return {
        name: [
            {"item": item, "count": count}
            for item, count in sorted(values.items(), key=lambda pair: (-pair[1], pair[0]))[:40]
        ]
        for name, values in facets.items()
    }


@router.post("/ingest", dependencies=[Depends(require_service_token)])
def ingest_inventory(
    source: str = Query(default="marketcheck", pattern="^(marketcheck|mock)$"),
    limit: int = Query(default=100, ge=1, le=500),
    start: int = Query(default=0, ge=0),
    zip_code: str | None = Query(default=None),
    radius: int | None = Query(default=None, ge=1, le=500),
    make: str | None = Query(default=None),
    model: str | None = Query(default=None),
    body_type: str | None = Query(default=None),
    min_price: float | None = Query(default=None),
    max_price: float | None = Query(default=None),
    year: int | None = Query(default=None),
    db: Session = Depends(get_db),
) -> dict:
    if source == "mock":
        inserted = seed_inventory(db)
        db.commit()
        return ok({"inserted": inserted, "mode": "mock-seed", "source": source})

    search_params = {
        "zip": zip_code,
        "radius": radius,
        "make": make,
        "model": model,
        "body_type": body_type,
        "car_type": body_type,
        "price_range": f"{int(min_price)}-{int(max_price)}" if min_price is not None and max_price is not None else None,
        "year": year,
    }
    client = _marketcheck_client()
    report = ingest_marketcheck_inventory(
        db,
        client=client,
        limit=limit,
        start=start,
        search_params=search_params,
    )
    db.commit()
    return ok(report.to_dict())


@router.get("/stats")
def inventory_stats(db: Session = Depends(get_db)) -> dict:
    total = db.scalar(select(func.count(Vehicle.vin))) or 0
    available = db.scalar(select(func.count(Vehicle.vin)).where(Vehicle.available.is_(True))) or 0
    avg_price = db.scalar(select(func.avg(Vehicle.price_asking))) or 0
    by_source_rows = db.execute(
        select(Vehicle.source_type, func.count(Vehicle.vin))
        .group_by(Vehicle.source_type)
        .order_by(func.count(Vehicle.vin).desc())
    ).all()
    by_source = {str(source or "unknown"): count for source, count in by_source_rows}
    return ok({"total": total, "available": available, "avg_price": round(float(avg_price), 2), "by_source": by_source})


@router.get("/facets")
def inventory_facets(
    q: str | None = Query(default=None),
    make: str | None = Query(default=None),
    model: str | None = Query(default=None),
    make_model_pairs: str | None = Query(default=None),
    trim: str | None = Query(default=None),
    body_type: str | None = Query(default=None),
    state: str | None = Query(default=None, min_length=2, max_length=2),
    inventory_type: str | None = Query(default=None),
    source_type: str | None = Query(default=None),
    exterior_color: str | None = Query(default=None),
    interior_color: str | None = Query(default=None),
    min_price: float | None = Query(default=None),
    max_price: float | None = Query(default=None),
    min_year: int | None = Query(default=None),
    max_year: int | None = Query(default=None),
    min_miles: int | None = Query(default=None),
    max_miles: int | None = Query(default=None),
    zip_code: str | None = Query(default=None),
    radius: int | None = Query(default=None, ge=1, le=500),
    has_images: bool | None = Query(default=True),
    use_marketcheck: bool = Query(default=True),
    db: Session = Depends(get_db),
) -> dict:
    taxonomy = get_inventory_taxonomy_facets(
        db,
        min_year=min_year,
        max_year=max_year,
        make=make,
        model=model,
    )
    if use_marketcheck and settings.has_marketcheck:
        client = _marketcheck_client()
        params = _build_marketcheck_search_params(
            q=q,
            make=make,
            model=model,
            trim=trim,
            body_type=body_type,
            state=state,
            min_price=min_price,
            max_price=max_price,
            min_year=min_year,
            max_year=max_year,
            has_images=has_images,
            exterior_color=exterior_color,
            interior_color=interior_color,
            drivetrain=None,
            fuel_type=None,
            transmission=None,
            inventory_type=inventory_type,
            certified=None,
            single_owner=None,
            clean_title=None,
            min_dom=None,
            max_dom=None,
            zip_code=zip_code,
            radius=radius,
        )
        try:
            payload = client.get_facets(params=params, facets=FACET_FIELDS)
            raw_facets = payload.get("facets", {}) if isinstance(payload, dict) else {}
            facets = {name: _parse_facet_buckets(raw_facets.get(name)) for name in FACET_FIELDS}
            return ok(
                {
                    "source": "marketcheck",
                    "num_found": payload.get("num_found", 0) if isinstance(payload, dict) else 0,
                    "facets": facets,
                    "taxonomy": taxonomy,
                }
            )
        except Exception:
            pass

    return ok(
        {
            "source": "local",
            "num_found": 0,
            "facets": _local_facets(
                db,
                q=q,
                make=make,
                model=model,
                make_model_pairs=make_model_pairs,
                trim=trim,
                state=state,
                body_type=body_type,
                inventory_type=inventory_type,
                min_price=min_price,
                max_price=max_price,
                min_year=min_year,
                max_year=max_year,
                min_miles=min_miles,
                max_miles=max_miles,
                exterior_color=exterior_color,
                interior_color=interior_color,
                zip_code=zip_code,
                radius=radius,
                has_images=has_images,
                source_type=source_type,
            ),
            "taxonomy": taxonomy,
        }
    )


@router.post("/taxonomy/sync", dependencies=[Depends(require_service_token)])
def sync_inventory_taxonomy(
    start_year: int = Query(default=MIN_TAXONOMY_YEAR, ge=MIN_TAXONOMY_YEAR, le=2100),
    end_year: int = Query(default=datetime.now(UTC).year + 1, ge=MIN_TAXONOMY_YEAR, le=2100),
    db: Session = Depends(get_db),
) -> dict:
    if not settings.has_marketcheck:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="MarketCheck live taxonomy sync is not configured",
        )

    report = sync_marketcheck_taxonomy_cache(
        db,
        client=_marketcheck_client(),
        start_year=start_year,
        end_year=end_year,
    )
    db.commit()
    return ok(report.to_dict())


@router.get("/taxonomy/list")
def list_taxonomy_routes(db: Session = Depends(get_db)) -> dict:
    """Return all unique make, make/model, make/model/trim combos for SEO sitemap generation."""
    rows = db.execute(
        select(
            VehicleTaxonomyCache.make,
            VehicleTaxonomyCache.model,
            VehicleTaxonomyCache.trim,
        ).where(VehicleTaxonomyCache.active.is_(True))
        .distinct()
        .order_by(VehicleTaxonomyCache.make, VehicleTaxonomyCache.model, VehicleTaxonomyCache.trim)
    ).all()
    routes = [{"make": r[0], "model": r[1], "trim": r[2] or ""} for r in rows]
    return ok({"routes": routes, "count": len(routes)})


@router.get("/hot-deals/active")
def active_hot_deals(
    limit: int = Query(default=12, ge=1, le=50),
    db: Session = Depends(get_db),
) -> dict:
    return ok({"items": get_active_hot_deals(db, limit=limit)})


class _ParseQueryBody(BaseModel):
    query: str = ""


@router.post("/parse-query")
def parse_natural_language_query(body: _ParseQueryBody) -> dict:
    """Parse a natural-language vehicle description into structured search filters."""
    from app.services.nlp_query_service import parse_vehicle_query

    query = body.query.strip()
    if not query:
        return ok({"filters": {}, "parsed": False, "parse_method": "none", "raw_query": ""})

    result = parse_vehicle_query(query)
    filters = {
        k: v
        for k, v in result.model_dump().items()
        if v is not None and k not in ("raw_query", "parsed", "parse_method")
    }

    return ok({
        "filters": filters,
        "parsed": result.parsed,
        "parse_method": result.parse_method,
        "raw_query": result.raw_query,
    })


@router.get("/search")
def search_inventory(
    q: str | None = Query(default=None),
    make: str | None = Query(default=None),
    model: str | None = Query(default=None),
    make_model_pairs: str | None = Query(default=None),
    trim: str | None = Query(default=None),
    body_type: str | None = Query(default=None),
    inventory_type: str | None = Query(default=None),
    certified: bool | None = Query(default=None),
    source_type: str | None = Query(default=None),
    state: str | None = Query(default=None, min_length=2, max_length=2),
    exterior_color: str | None = Query(default=None),
    interior_color: str | None = Query(default=None),
    drivetrain: str | None = Query(default=None),
    fuel_type: str | None = Query(default=None),
    transmission: str | None = Query(default=None),
    single_owner: bool | None = Query(default=None),
    clean_title: bool | None = Query(default=None),
    min_dom: int | None = Query(default=None, ge=0),
    max_dom: int | None = Query(default=None, ge=0),
    min_price: float | None = Query(default=None),
    max_price: float | None = Query(default=None),
    min_year: int | None = Query(default=None),
    max_year: int | None = Query(default=None),
    min_miles: int | None = Query(default=None),
    max_miles: int | None = Query(default=None),
    zip_code: str | None = Query(default=None),
    radius: int | None = Query(default=None, ge=1, le=500),
    has_images: bool | None = Query(default=None),
    sort_by: str = Query(default="updated_at", pattern="^(updated_at|price_asking|year|odometer)$"),
    sort_dir: str = Query(default="desc", pattern="^(asc|desc)$"),
    live_sync: bool = Query(default=False),
    sync_limit: int = Query(default=72, ge=1, le=300),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=24, ge=1, le=100),
    db: Session = Depends(get_db),
) -> dict:
    # ── NLP parsing for free-text q field ──────────────────────────
    # If the user typed something in the free-form search and didn't set
    # structured filters, run it through the NLP parser to extract filters.
    nlp_parsed = None
    is_vin_search = False
    if q and q.strip() and not any([make, model, trim]):
        from app.services.nlp_query_service import parse_vehicle_query
        nlp_parsed = parse_vehicle_query(q.strip())
        if nlp_parsed.parsed:
            if nlp_parsed.vin:
                # VIN search — override q to just the VIN for exact match
                q = nlp_parsed.vin
                is_vin_search = True
            else:
                # Structured filters extracted — apply them and clear q
                make = make or nlp_parsed.make
                model = model or nlp_parsed.model
                trim = trim or nlp_parsed.trim
                body_type = body_type or nlp_parsed.body_type
                min_year = min_year if min_year is not None else nlp_parsed.min_year
                max_year = max_year if max_year is not None else nlp_parsed.max_year
                min_price = min_price if min_price is not None else nlp_parsed.min_price
                max_price = max_price if max_price is not None else nlp_parsed.max_price
                min_miles = min_miles if min_miles is not None else nlp_parsed.min_miles
                max_miles = max_miles if max_miles is not None else nlp_parsed.max_miles
                drivetrain = drivetrain or nlp_parsed.drivetrain
                fuel_type = fuel_type or nlp_parsed.fuel_type
                transmission = transmission or nlp_parsed.transmission
                state = state or nlp_parsed.state
                exterior_color = exterior_color or nlp_parsed.exterior_color
                interior_color = interior_color or nlp_parsed.interior_color
                if nlp_parsed.certified is not None and certified is None:
                    certified = nlp_parsed.certified
                if nlp_parsed.single_owner is not None and single_owner is None:
                    single_owner = nlp_parsed.single_owner
                if nlp_parsed.clean_title is not None and clean_title is None:
                    clean_title = nlp_parsed.clean_title
                # Clear q so it doesn't also run the LIKE filter
                q = None

    # Also detect VIN from raw q (e.g. user typed VIN directly in search box)
    if not is_vin_search and q and len(q.strip()) == 17 and q.strip().isalnum():
        is_vin_search = True

    sync: dict[str, Any] = {
        "requested": live_sync,
        "enabled": bool(settings.has_marketcheck),
        "executed": False,
        "mode": "disabled",
        "fetched": 0,
        "inserted": 0,
        "updated": 0,
        "skipped_priority": 0,
        "skipped_invalid": 0,
        "error": None,
        "synced_vins": [],
    }
    effective_min_dom = min_dom
    if effective_min_dom is None and _should_apply_default_aged_inventory_min(source_type):
        effective_min_dom = AGED_INVENTORY_MIN_DOM

    # Don't use MarketCheck for auction/OVE searches - use local database only
    is_auction_search = source_type and source_type.lower() in ['auction', 'ove', PUBLIC_AUCTION_SOURCE.lower()]
    is_any_source = not source_type or not source_type.strip()

    # For "Any" source searches, count local auction results first.
    # Only backfill from MarketCheck if we have fewer than 25 auction matches.
    _auction_backfill_threshold = 25
    should_sync_marketcheck = live_sync and settings.marketcheck_api_key and not is_auction_search and not is_vin_search
    if should_sync_marketcheck and is_any_source:
        auction_count_stmt = select(func.count()).select_from(Vehicle).where(
            Vehicle.available.is_(True),
            func.lower(Vehicle.source_type).in_(
                [InventorySourceType.AUCTION.value, InventorySourceType.OVE.value]
            ),
        )
        auction_count_stmt = _apply_make_model_filters(auction_count_stmt, make, model, make_model_pairs)
        if min_year is not None:
            auction_count_stmt = auction_count_stmt.where(Vehicle.year >= min_year)
        if max_year is not None:
            auction_count_stmt = auction_count_stmt.where(Vehicle.year <= max_year)
        if max_miles is not None:
            auction_count_stmt = auction_count_stmt.where(Vehicle.odometer <= max_miles)
        auction_count_stmt = _apply_zip_radius_filter(auction_count_stmt, zip_code, radius)
        local_auction_count = db.scalar(auction_count_stmt) or 0
        if local_auction_count >= _auction_backfill_threshold:
            should_sync_marketcheck = False

    if should_sync_marketcheck:
        client = _marketcheck_client()
        search_params = _build_marketcheck_search_params(
            q=q,
            make=make,
            model=model,
            trim=trim,
            body_type=body_type,
            state=state,
            min_price=min_price,
            max_price=max_price,
            min_year=min_year,
            max_year=max_year,
            has_images=has_images,
            exterior_color=exterior_color,
            interior_color=interior_color,
            drivetrain=drivetrain,
            fuel_type=fuel_type,
            transmission=transmission,
            inventory_type=inventory_type,
            certified=certified,
            single_owner=single_owner,
            clean_title=clean_title,
            min_dom=effective_min_dom,
            max_dom=max_dom,
            zip_code=zip_code,
            radius=radius,
        )
        try:
            report = ingest_marketcheck_inventory(
                db,
                client=client,
                limit=sync_limit,
                start=max((page - 1) * per_page, 0),
                search_params=search_params,
            )
            db.commit()
            report_data = report.to_dict()
            sync.update({"executed": True, **report_data})
        except Exception as exc:  # pragma: no cover - integration failures are environment dependent
            db.rollback()
            sync.update(
                {
                    "executed": True,
                    "mode": "fallback",
                    "error": _friendly_live_sync_error(exc),
                }
            )

    # VIN searches return a specific vehicle regardless of availability status
    if is_vin_search:
        stmt = select(Vehicle).where(
            or_(
                Vehicle.quality_firewall_pass.is_(True),
                Vehicle.quality_firewall_pass.is_(None),
            ),
        )
    else:
        stmt = select(Vehicle).where(
            Vehicle.available.is_(True),
            or_(
                Vehicle.quality_firewall_pass.is_(True),
                Vehicle.quality_firewall_pass.is_(None),
            ),
        )
    if q:
        clean_q = q.strip()
        # VIN exact match (17 alphanumeric characters)
        if len(clean_q) == 17 and clean_q.isalnum():
            stmt = stmt.where(func.upper(Vehicle.vin) == clean_q.upper())
        else:
            text = f"%{clean_q.lower()}%"
            stmt = stmt.where(
                or_(
                    func.lower(Vehicle.vin).like(text),
                    func.lower(Vehicle.make).like(text),
                    func.lower(Vehicle.model).like(text),
                    func.lower(func.coalesce(Vehicle.trim, "")).like(text),
                )
            )
    stmt = _apply_make_model_filters(stmt, make, model, make_model_pairs)
    trims = _split_csv(trim)
    if trims:
        stmt = stmt.where(func.lower(func.coalesce(Vehicle.trim, "")).in_(trims))
    body_types = _split_csv(body_type)
    if body_types:
        stmt = stmt.where(_inferred_body_type_expr().in_(body_types))
    if exterior_color:
        ext_col_expr = func.lower(func.coalesce(Vehicle.features_normalized["exterior_color"].as_string(), ""))
        ext_parts = _split_csv(exterior_color)
        if ext_parts:
            stmt = stmt.where(or_(*[ext_col_expr.like(f"%{p}%") for p in ext_parts]))
    if interior_color:
        int_col_expr = func.lower(func.coalesce(Vehicle.features_normalized["interior_color"].as_string(), ""))
        int_parts = _split_csv(interior_color)
        if int_parts:
            stmt = stmt.where(or_(*[int_col_expr.like(f"%{p}%") for p in int_parts]))
    if inventory_type:
        stmt = stmt.where(
            func.lower(func.coalesce(Vehicle.features_normalized["inventory_type"].as_string(), "")) == inventory_type.lower()
        )
    if certified is not None:
        certified_expr = func.lower(func.coalesce(Vehicle.features_normalized["certified"].as_string(), ""))
        if certified:
            stmt = stmt.where(certified_expr.in_(["true", "1", "yes"]))
        else:
            stmt = stmt.where(certified_expr.in_(["false", "0", "no"]))
    stmt = _apply_source_type_filter(stmt, source_type)
    if state:
        stmt = stmt.where(func.lower(Vehicle.location_state) == state.lower())
    if drivetrain:
        stmt = stmt.where(func.lower(func.coalesce(Vehicle.drivetrain, "")) == drivetrain.lower())
    dom_expr = _aged_inventory_dom_expr()
    auction_expr = func.lower(Vehicle.source_type).in_([InventorySourceType.OVE.value, InventorySourceType.AUCTION.value])
    advertised_price = _advertised_price_expr()
    if min_price is not None:
        stmt = stmt.where(advertised_price >= min_price)
    if max_price is not None:
        stmt = stmt.where(advertised_price <= max_price)
    if min_year is not None:
        stmt = stmt.where(Vehicle.year >= min_year)
    if max_year is not None:
        stmt = stmt.where(Vehicle.year <= max_year)
    if min_miles is not None:
        stmt = stmt.where(Vehicle.odometer >= min_miles)
    if max_miles is not None:
        stmt = stmt.where(Vehicle.odometer <= max_miles)
    if effective_min_dom is not None:
        stmt = stmt.where(or_(auction_expr, dom_expr >= effective_min_dom))
    if max_dom is not None:
        stmt = stmt.where(or_(auction_expr, dom_expr <= max_dom))
    if has_images is True:
        stmt = stmt.where(func.coalesce(func.json_array_length(Vehicle.images), 0) > 0)
    # VIN searches find a specific vehicle — don't limit by geography
    if not is_vin_search:
        stmt = _apply_zip_radius_filter(stmt, zip_code, radius)

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0

    sort_columns = {
        "updated_at": Vehicle.updated_at,
        "price_asking": advertised_price,
        "year": Vehicle.year,
        "odometer": Vehicle.odometer,
    }
    order_column = sort_columns[sort_by]
    user_order = asc(order_column) if sort_dir == "asc" else desc(order_column)

    # When browsing all sources, show auction/OVE vehicles before MarketCheck
    if is_any_source:
        auction_first = case(
            (func.lower(Vehicle.source_type).in_(
                [InventorySourceType.AUCTION.value, InventorySourceType.OVE.value]
            ), 0),
            else_=1,
        )
        order_by = (auction_first, user_order)
    else:
        order_by = (user_order,)

    offset = (page - 1) * per_page
    rows = db.scalars(stmt.order_by(*order_by).offset(offset).limit(per_page)).all()

    total_pages = max(1, (total + per_page - 1) // per_page) if total else 0

    # Sync ChromeData images for page-1 rows that need them, so the first
    # page renders with color-matched factory photos immediately.
    if settings.has_chromedata_media:
        from app.services.chromedata_service import build_chromedata_manifest, sync_chromedata_source_assets

        backfill_vins: list[str] = []
        for row in rows:
            if not row.vin:
                continue
            has_cd = (row.features_normalized or {}).get("chromedata_style_id")
            if has_cd:
                continue
            # Check if chromedata assets already cached
            existing_cd = db.scalar(
                select(VehicleImageAsset.id).where(
                    VehicleImageAsset.vin == row.vin,
                    VehicleImageAsset.source_kind == "chromedata",
                    VehicleImageAsset.active == True,
                ).limit(1)
            )
            if existing_cd:
                continue
            backfill_vins.append(row.vin)

        # Fetch synchronously for this page (fast — results visible immediately)
        for vin in backfill_vins:
            try:
                vehicle_rec = db.get(Vehicle, vin)
                if vehicle_rec:
                    manifest = build_chromedata_manifest(vehicle_rec, detail_level="card")
                    if manifest:
                        sync_chromedata_source_assets(db, vehicle=vehicle_rec, manifest=manifest)
            except Exception:
                logger.debug("ChromeData sync failed for vin=%s", vin, exc_info=True)
        if backfill_vins:
            db.commit()

        # Dispatch background Celery task for remaining pages' VINs
        if total and total > per_page:
            remaining_vins: list[str] = []
            remaining_rows = db.scalars(
                stmt.order_by(*order_by).offset(offset + per_page).limit(min(total - per_page, 200))
            ).all()
            for r in remaining_rows:
                if r.vin and not (r.features_normalized or {}).get("chromedata_style_id"):
                    remaining_vins.append(r.vin)
            if remaining_vins:
                try:
                    from app.tasks.jobs import chromedata_backfill
                    chromedata_backfill.delay(remaining_vins)
                except Exception:
                    pass  # Celery not available — will fetch on demand

    items: list[dict[str, Any]] = []
    for row in rows:
        media = resolve_vehicle_card_media(db, vehicle=row)
        normalized = row.features_normalized or {}
        pricing = _pricing_breakdown(row.price_asking)
        items.append(
            {
                "vin": row.vin,
                "public_slug": row.public_slug,
                "listing_id": row.listing_id,
                "year": row.year,
                "make": row.make,
                "model": row.model,
                "trim": row.trim,
                "body_type": row.body_type,
                "drivetrain": row.drivetrain,
                "price_asking": pricing["advertised_price"],
                "source_price": pricing["source_price"],
                "buy_fee": pricing["buy_fee"],
                "margin": pricing["margin"],
                "pricing": pricing,
                "odometer": row.odometer,
                "location_state": row.location_state,
                "location_zip": row.location_zip,
                "source_type": row.source_type,
                "source_category": PUBLIC_AUCTION_SOURCE if _is_auction_source(row.source_type) else PUBLIC_RETAIL_SOURCE,
                "source_filter_value": _public_source_value(row.source_type),
                "source_label": _public_source_label(row.source_type),
                "thumbnail": media.thumbnail,
                "reference_pending": media.reference_pending,
                "evox_pending": media.reference_pending,
                "dealer_photos_gated": media.dealer_photos_gated,
                "gated_photo_count": media.gated_photo_count,
                "images_count": len(row.images or []),
                "features_preview": (row.features_raw or [])[:5],
                "display_mode": media.display_mode.value,
                "inspection_status": media.inspection_status.value,
                "has_inspection_report": media.has_inspection_report,
                "exterior_color": normalized.get("exterior_color") or None,
                "interior_color": normalized.get("interior_color") or None,
                "fuel_type": normalized.get("fuel_type") or None,
                "transmission": normalized.get("transmission") or None,
                "engine_type": normalized.get("engine_type") or row.engine_type,
                "cylinders": row.cylinders,
                "drivetrain": normalized.get("drivetrain") or row.drivetrain,
                "odometer_units": normalized.get("odometer_units") or "mi",
                "inventory_type": normalized.get("inventory_type"),
                "days_on_market": normalized.get("days_on_market"),
                "single_owner": normalized.get("single_owner"),
                "clean_title": normalized.get("clean_title"),
                "certified": normalized.get("certified"),
                "dealer_name": normalized.get("dealer_name"),
                "city": normalized.get("city"),
                "auction_house": normalized.get("auction_house"),
                "pickup_location": normalized.get("pickup_location"),
                "inventory_status": normalized.get("status"),
                "inventory_label": normalized.get("inventory"),
                "badges": _compute_badges(
                    row.year, row.odometer, row.price_asking,
                    _normalized_pick(normalized, "mmr", "mmr_value", "manheim_mmr"),
                ),
            }
        )

    return ok(
        {
            "items": items,
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total": total,
                "total_pages": total_pages,
                "has_next": page < total_pages,
                "has_prev": page > 1 and total_pages > 0,
            },
            "sync": sync,
        }
    )



class ReferenceBatchRequest(BaseModel):
    vins: list[str]


@router.post("/reference-images/batch")
@router.post("/evox-batch")
def batch_fetch_reference_images(
    body: ReferenceBatchRequest,
    db: Session = Depends(get_db),
) -> dict:
    """Batch-fetch ChromeData reference images for up to 10 VINs.

    Called by the frontend after search results load when vehicles have
    reference_pending=true. Fetches factory reference images from
    ChromeData, caches them, and returns updated image URLs per VIN.
    """
    from app.services.chromedata_service import (
        CHROMEDATA_SOURCE_KIND,
        batch_build_chromedata_manifests,
        chromedata_assets_need_refresh,
        sync_chromedata_source_assets,
    )

    if not settings.has_chromedata_media:
        return ok({"results": {}})

    vins = [v.strip().upper() for v in body.vins[:10] if v.strip()]
    if not vins:
        return ok({"results": {}})

    # Load vehicles and filter to those without cached ChromeData card assets
    vehicles: list[Vehicle] = []
    for vin in vins:
        vehicle = db.get(Vehicle, vin)
        if not vehicle:
            continue
        existing_assets = db.scalars(
            select(VehicleImageAsset).where(
                VehicleImageAsset.vin == vin,
                VehicleImageAsset.tier == ImageTier.SOURCE_CACHE,
                VehicleImageAsset.source_kind == CHROMEDATA_SOURCE_KIND,
                VehicleImageAsset.role.in_(["hero", "gallery"]),
                VehicleImageAsset.active.is_(True),
            )
        ).all()
        if chromedata_assets_need_refresh(vehicle, existing_assets):
            vehicles.append(vehicle)

    if not vehicles:
        return ok({"results": {}})

    manifests = batch_build_chromedata_manifests(vehicles, detail_level="card")

    results: dict[str, dict[str, Any]] = {}
    for vehicle in vehicles:
        manifest = manifests.get(vehicle.vin)
        if not manifest:
            continue
        sync_chromedata_source_assets(db, vehicle=vehicle, manifest=manifest)
        results[vehicle.vin] = {
            "hero_url": manifest.hero_url,
            "gallery_urls": manifest.gallery_urls,
            "match_level": manifest.match_level,
            "color_info": {
                "color_code": manifest.color_info.color_code,
                "color_title": manifest.color_info.description,
                "color_simpletitle": manifest.color_info.generic_desc,
                "is_exact_match": manifest.color_info.is_exact_match,
            } if manifest.color_info else None,
        }

    db.commit()
    return ok({"results": results})


@router.get("/{identifier}")
def get_inventory_vehicle(
    identifier: str,
    db: Session = Depends(get_db),
    current_user: User | None = Depends(get_optional_user),
) -> dict:
    from app.services.vin_slug_service import resolve_vehicle_identifier

    vehicle = resolve_vehicle_identifier(db, identifier)
    if not vehicle:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vehicle not found")
    vin = vehicle.vin

    # Check if the vehicle is in the user's garage
    is_in_garage = False
    active_deal = None
    if current_user:
        active_deal = db.scalar(
            select(Deal).where(
                Deal.user_id == current_user.id,
                Deal.stage.notin_(["CLOSED_WON", "CLOSED_LOST"]),
            ).order_by(Deal.created_at.desc())
        )
        if active_deal:
            garage_item = db.scalar(
                select(GarageItem).where(
                    GarageItem.deal_id == active_deal.id,
                    GarageItem.vin == vin.upper(),
                )
            )
            is_in_garage = garage_item is not None

    # Dealer photos are gated behind garage membership — the user must add
    # the vehicle to their garage before dealer images are unlocked.
    allow_protected = is_in_garage
    display_context = resolve_vehicle_display_context(
        db,
        vehicle=vehicle,
        is_garage_view=is_in_garage,
        allow_protected_photos=allow_protected,
    )

    # Lazy-load full ChromeData reference assets when detail imagery is not cached yet.
    has_chromedata_card = display_context.get("has_chromedata_stock")
    has_chromedata_detail = bool(display_context.get("chromedata_detail_images"))
    should_fetch_chromedata_detail = settings.has_chromedata_media and (
        not has_chromedata_card
        or not has_chromedata_detail
        or bool(display_context.get("reference_pending"))
    )
    if should_fetch_chromedata_detail:
        try:
            from app.services.chromedata_service import build_chromedata_manifest, sync_chromedata_source_assets

            full_manifest = build_chromedata_manifest(vehicle, detail_level="full")
            if full_manifest:
                sync_chromedata_source_assets(db, vehicle=vehicle, manifest=full_manifest)
                db.commit()
                display_context = resolve_vehicle_display_context(
                    db,
                    vehicle=vehicle,
                    is_garage_view=is_in_garage,
                    allow_protected_photos=allow_protected,
                )
        except Exception:
            logger.warning("ChromeData detail fetch failed for vin=%s", vehicle.vin, exc_info=True)

    public_gallery = display_context.get("gallery_images") or []
    resolved_images = public_gallery or ([] if display_context.get("dealer_photos_gated") else (vehicle.images or []))
    hero_image = display_context.get("hero_image") or (resolved_images[0] if resolved_images else None)

    listing_meta: dict[str, Any] = {}
    if settings.has_marketcheck and vehicle.source_type == "marketcheck":
        try:
            client = _marketcheck_client()
            listing = _fetch_marketcheck_listing_by_vehicle(client, vehicle)
            listing_meta = _extract_listing_metadata(listing)
        except Exception:
            listing_meta = {}

    history_enrichment = None
    history_listing_meta: dict[str, Any] = {}
    if _is_auction_source(vehicle.source_type):
        history_enrichment = db.get(VehicleHistoryEnrichment, vehicle.vin)
        history_listing_meta = enrichment_metadata_from_record(history_enrichment)

        if settings.has_marketcheck and is_thin_listing(vehicle, history_listing_meta) and not history_listing_meta:
            try:
                history_enrichment = enrich_vehicle_history(db, vehicle=vehicle, force=False)
                db.commit()
                history_listing_meta = enrichment_metadata_from_record(history_enrichment)
            except Exception:
                db.rollback()
                logger.debug("cached history enrichment refresh failed for vin=%s", vehicle.vin, exc_info=True)
                history_listing_meta = {}

        # Fall back to direct history lookup for thin auction rows if the cache is still empty.
        if settings.has_marketcheck and not history_listing_meta and not listing_meta:
            history_listing_meta = _try_marketcheck_history_enrichment(vehicle)

    listing_meta = merge_listing_metadata(listing_meta, history_listing_meta)

    # ── NHTSA VIN decode enrichment ──
    nhtsa_categories: dict[str, Any] = {}
    try:
        nhtsa = NHTSAClient()
        decode_result = nhtsa.decode_vin(vehicle.vin)
        if decode_result.year:  # valid decode
            nhtsa_categories = categorize_decode(decode_result)
    except Exception:
        logger.warning("NHTSA decode failed for %s", vehicle.vin, exc_info=True)

    db_features = _normalize_feature_list(vehicle.features_raw or [])
    listing_features = listing_meta.get("features") or []
    merged_features: list[str] = []
    seen: set[str] = set()
    for source in (db_features, listing_features):
        for value in source:
            key = value.lower()
            if key in seen:
                continue
            seen.add(key)
            merged_features.append(value)

    normalized = vehicle.features_normalized or {}
    pricing = _pricing_breakdown(vehicle.price_asking)
    ove_detail = db.get(OveVehicleDetail, vehicle.vin)
    ove_payload = None
    # CR data is visible to admins, pre-approved users, and users with eligible funding state
    _can_view_cr = False
    if current_user:
        if is_admin_user(current_user):
            _can_view_cr = True
        elif current_user.is_preapproved:
            if not current_user.preapproved_until or current_user.preapproved_until >= datetime.now(UTC):
                _can_view_cr = True
        else:
            active_deal = db.scalar(
                select(Deal).where(
                    Deal.user_id == current_user.id,
                    Deal.stage.notin_(["CLOSED_WON", "CLOSED_LOST"]),
                ).order_by(Deal.created_at.desc())
            )
            if active_deal and active_deal.funding_state in {
                FundingState.PRE_APPROVED, FundingState.TERMS_ACCEPTED,
                FundingState.FINAL_APPROVAL_PENDING, FundingState.FULLY_FUNDED,
                FundingState.CASH_BUYER,
            }:
                _can_view_cr = True
    if ove_detail:
        ove_payload = {
            "source_platform": ove_detail.source_platform.value,
            "seller_comments": ove_detail.seller_comments,
            "images": (ove_detail.images_json or []) if _can_view_cr else [],
            "condition_report": (ove_detail.condition_report_json or {}) if _can_view_cr else {},
            "listing_snapshot": (ove_detail.listing_snapshot_json or {}) if _can_view_cr else {},
            "sync_metadata": (ove_detail.sync_metadata_json or {}) if _can_view_cr else {},
            "page_url": ove_detail.page_url if _can_view_cr else None,
            "last_synced_at": ove_detail.last_synced_at,
        }

    raw_listing_comment = (
        listing_meta.get("seller_comments_original")
        or listing_meta.get("seller_comments")
        or listing_meta.get("description")
    )
    rewritten_listing_comment = (
        listing_meta.get("seller_comments")
        if listing_meta.get("seller_comments_original")
        else None
    )
    if raw_listing_comment and not rewritten_listing_comment:
        rewritten_listing_comment = get_cached_vehicle_seller_comment(vehicle, raw_listing_comment)
        if not rewritten_listing_comment:
            rewritten_listing_comment, rewrite_provider = build_virtualcarhub_seller_comment(
                vehicle=vehicle,
                source_text=raw_listing_comment,
                metadata=listing_meta,
            )
            if rewritten_listing_comment:
                try:
                    if cache_vehicle_seller_comment(
                        vehicle,
                        source_text=raw_listing_comment,
                        rewritten_text=rewritten_listing_comment,
                        provider=rewrite_provider,
                        source_kind="marketcheck_current" if vehicle.source_type == "marketcheck" else "listing_metadata",
                    ):
                        db.commit()
                        normalized = vehicle.features_normalized or normalized
                except Exception:
                    db.rollback()
                    logger.debug("seller comment cache persist failed for vin=%s", vehicle.vin, exc_info=True)

    seller_comments = (
        (ove_detail.seller_comments if ove_detail else None)
        or rewritten_listing_comment
        or raw_listing_comment
    )
    active_hot_deal = db.scalar(
        select(HotDeal)
        .where(
            HotDeal.vin == vehicle.vin,
            HotDeal.is_active.is_(True),
            HotDeal.expires_at > datetime.now(UTC),
        )
        .order_by(HotDeal.deal_rank.asc(), HotDeal.deal_delta.desc())
        .limit(1)
    )

    public_display_context = dict(display_context)
    if not _can_view_cr:
        public_display_context["condition_report"] = {}
        public_display_context["buyer_protection"] = {}

    return ok(
        {
            "vin": vehicle.vin,
            "public_slug": vehicle.public_slug,
            "listing_id": vehicle.listing_id,
            "year": vehicle.year,
            "make": vehicle.make,
            "model": vehicle.model,
            "trim": vehicle.trim,
            "body_type": vehicle.body_type,
            "sub_body_type": vehicle.sub_body_type,
            "engine_type": vehicle.engine_type,
            "cylinders": vehicle.cylinders,
            "forced_induction": vehicle.forced_induction,
            "drivetrain": vehicle.drivetrain,
            "mpg_combined": vehicle.mpg_combined,
            "ev_range": vehicle.ev_range,
            "towing_capacity_lbs": vehicle.towing_capacity_lbs,
            "odometer": vehicle.odometer,
            "condition_grade": vehicle.condition_grade,
            "price_asking": pricing["advertised_price"],
            "source_price": pricing["source_price"],
            "buy_fee": pricing["buy_fee"],
            "margin": pricing["margin"],
            "pricing": pricing,
            "price_wholesale_est": vehicle.price_wholesale_est,
            "location_zip": vehicle.location_zip,
            "location_state": vehicle.location_state,
            "source_type": vehicle.source_type,
            "source_category": PUBLIC_AUCTION_SOURCE if _is_auction_source(vehicle.source_type) else PUBLIC_RETAIL_SOURCE,
            "source_filter_value": _public_source_value(vehicle.source_type),
            "source_label": _public_source_label(vehicle.source_type),
            "images": [] if display_context.get("dealer_photos_gated") else (vehicle.images or []),
            "display_images": resolved_images,
            "hero_image": hero_image,
            "display_mode": display_context.get("mode"),
            "inspection_status": display_context.get("inspection_status"),
            "has_inspection_report": bool(display_context.get("has_inspection_report")),
            "is_in_garage": is_in_garage,
            "can_view_protected_photos": allow_protected,
            "protected_photo_access_message": protected_photo_access_message(user=current_user, deal=active_deal),
            "features_raw": merged_features,
            "features_full": merged_features,
            "high_value_features": listing_meta.get("high_value_features") or [],
            "feature_details": listing_meta.get("feature_details") or [],
            "high_value_feature_details": listing_meta.get("high_value_feature_details") or [],
            "options": listing_meta.get("options") or [],
            "option_details": listing_meta.get("option_details") or [],
            "option_packages": listing_meta.get("option_packages") or [],
            "option_package_details": listing_meta.get("option_package_details") or [],
            "photo_links": (listing_meta.get("photo_links") or []) if allow_protected else [],
            "photo_links_cached": (listing_meta.get("photo_links_cached") or []) if allow_protected else [],
            "supplemental_photo_links": (listing_meta.get("supplemental_photo_links") or []) if allow_protected else [],
            "description": listing_meta.get("description"),
            "exterior_color": normalized.get("exterior_color") or listing_meta.get("exterior_color") or None,
            "interior_color": normalized.get("interior_color") or listing_meta.get("interior_color") or None,
            "fuel_type": listing_meta.get("fuel_type") or normalized.get("fuel_type") or None,
            "transmission": (
                listing_meta.get("transmission")
                or normalized.get("transmission")
                or None
            ),
            "inventory_type": listing_meta.get("inventory_type") or normalized.get("inventory_type"),
            "days_on_market": listing_meta.get("days_on_market") or normalized.get("days_on_market"),
            "auction_house": _normalized_pick(normalized, "auction_house"),
            "pickup_location": _normalized_pick(normalized, "pickup_location"),
            "inventory_status": _normalized_pick(normalized, "status"),
            "inventory_label": _normalized_pick(normalized, "inventory"),
            "odometer_units": _normalized_pick(normalized, "odometer_units") or "mi",
            "transmission_type": (
                listing_meta.get("transmission")
                or normalized.get("transmission")
                or None
            ),
            "condition_report_grade": (
                _normalized_pick(normalized, "condition_report_grade", "condition_grade")
                or vehicle.condition_grade
                or ((ove_detail.condition_report_json or {}).get("overall_grade") if ove_detail else None)
                or ((ove_detail.condition_report_json or {}).get("grade") if ove_detail else None)
            ),
            "mmr": _normalized_pick(normalized, "mmr", "mmr_value", "manheim_mmr"),
            "badges": _compute_badges(
                vehicle.year, vehicle.odometer, vehicle.price_asking,
                _normalized_pick(normalized, "mmr", "mmr_value", "manheim_mmr"),
            ),
            "single_owner": (
                listing_meta.get("single_owner")
                if listing_meta.get("single_owner") is not None
                else normalized.get("single_owner")
            ),
            "clean_title": (
                listing_meta.get("clean_title")
                if listing_meta.get("clean_title") is not None
                else normalized.get("clean_title")
            ),
            "certified": (
                listing_meta.get("certified")
                if listing_meta.get("certified") is not None
                else normalized.get("certified")
            ),
            "dealer_name": listing_meta.get("dealer_name") or normalized.get("dealer_name"),
            "city": listing_meta.get("city") or normalized.get("city"),
            "features_normalized": normalized,
            "seller_comments": seller_comments,
            "condition_report": (ove_detail.condition_report_json if ove_detail else {}) if _can_view_cr else {},
            "condition_report_url": _extract_cr_url(ove_detail) if _can_view_cr else None,
            "listing_snapshot": (ove_detail.listing_snapshot_json if ove_detail else {}) if _can_view_cr else {},
            "hot_deal": serialize_hot_deal(active_hot_deal) if active_hot_deal else None,
            "ove_detail": ove_payload,
            "history_enrichment": {
                "status": history_enrichment.status,
                "source_listing_id": history_enrichment.source_listing_id,
                "source_url": history_enrichment.source_url,
                "last_enriched_at": _to_iso(history_enrichment.last_enriched_at),
            } if history_enrichment else None,
            "available": vehicle.available,
            "last_seen_active": vehicle.last_seen_active,
            "updated_at": vehicle.updated_at,
            "display_context": public_display_context,
            "is_in_garage": is_in_garage,
            "nhtsa_decoded": nhtsa_categories,
        }
    )


@router.get("/{identifier}/payment-estimate")
def get_inventory_vehicle_payment_estimate(
    identifier: str,
    credit_tier: str = Query(default=DEFAULT_CREDIT_TIER_ID),
    months: int = Query(default=DEFAULT_LOAN_TERM_MONTHS, ge=12, le=96),
    db: Session = Depends(get_db),
) -> dict:
    from app.services.vin_slug_service import resolve_vehicle_identifier

    vehicle = resolve_vehicle_identifier(db, identifier)
    if not vehicle:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vehicle not found")

    pricing = _pricing_breakdown(vehicle.price_asking)
    principal = _to_float(pricing.get("advertised_price")) or 0.0
    return ok(
        {
            "vin": vehicle.vin,
            **build_payment_estimate(principal=principal, tier_id=credit_tier, months=months),
        }
    )


@router.get("/{identifier}/market-comparison")
def get_inventory_vehicle_market_comparison(
    identifier: str,
    db: Session = Depends(get_db),
) -> dict:
    from app.services.vin_slug_service import resolve_vehicle_identifier

    vehicle = resolve_vehicle_identifier(db, identifier)
    if not vehicle:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vehicle not found")

    if not vehicle.odometer or not vehicle.price_asking:
        return ok(
            {
                "vin": vehicle.vin,
                "generated_at": _to_iso(datetime.now(UTC)),
                "this_vehicle": {
                    "vin": vehicle.vin,
                    "label": f"{vehicle.year} {vehicle.make} {vehicle.model}{(' ' + vehicle.trim) if vehicle.trim else ''}",
                    "price": _pricing_breakdown(vehicle.price_asking)["advertised_price"],
                    "miles": vehicle.odometer,
                    "href": f"/vinventory/{vehicle.public_slug or vehicle.vin}",
                },
                "comparables": [],
                "national_average": None,
                "metrics": {
                    "available_units": None,
                    "market_days_supply": None,
                    "sold_units_45_days": None,
                },
                "sources": {
                    "local_comparable_count": 0,
                    "marketcheck_enabled": bool(settings.has_marketcheck),
                    "marketcheck_comparable_count": 0,
                    "mds_available": False,
                    "price_prediction_available": False,
                },
            }
        )

    cached_payload = _get_cached_market_comparison_payload(db, vehicle)
    if cached_payload is not None:
        return ok(cached_payload)

    payload = _build_market_comparison_payload(db, vehicle)
    _write_market_comparison_cache(db, vehicle, payload)
    return ok(payload)


@router.post("/history-enrichment/run", dependencies=[Depends(require_service_token)])
def run_inventory_history_enrichment(
    limit: int = Query(default=8, ge=1, le=50),
    force: bool = Query(default=False),
    vin: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> dict:
    vins = [vin.strip().upper()] if vin and vin.strip() else None
    return ok(run_history_enrichment_batch(db, limit=limit, force=force, vins=vins))


@router.post("/snapshot/run", dependencies=[Depends(require_service_token)])
def run_inventory_snapshot(
    states: str | None = Query(default=None),
) -> dict:
    from app.tasks.jobs import marketcheck_snapshot

    state_list = [state.upper() for state in _split_csv(states)] if states else None
    task = marketcheck_snapshot.delay(states=state_list)
    return ok({"task_id": str(task.id), "states": state_list or settings.snapshot_target_states})


@router.post("/stale-cleanup/run", dependencies=[Depends(require_service_token)])
def run_marketcheck_stale_cleanup(
    dry_run: bool = Query(default=True),
) -> dict:
    from app.tasks.jobs import marketcheck_stale_cleanup

    task = marketcheck_stale_cleanup.delay(dry_run=dry_run)
    return ok({"task_id": str(task.id), "dry_run": dry_run})


@router.post("/images/cache/run", dependencies=[Depends(require_service_token)])
def run_image_cache_to_s3(
    batch_size: int = Query(default=100, ge=1, le=1000),
) -> dict:
    from app.tasks.jobs import cache_images_to_s3_batch

    task = cache_images_to_s3_batch.delay(batch_size=batch_size)
    return ok({"task_id": str(task.id), "batch_size": batch_size})


@router.get("/{identifier}/similar")
def get_similar_vehicles(
    identifier: str,
    limit: int = Query(default=6, le=12),
    db: Session = Depends(get_db),
) -> dict:
    """Return vehicles similar to the given VIN based on make/model/price/year."""
    from app.services.vin_slug_service import resolve_vehicle_identifier

    vehicle = resolve_vehicle_identifier(db, identifier)
    if not vehicle:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vehicle not found")

    # Build query: same make, prefer same model, within ±3 years and ±30% price
    price = vehicle.price_asking or 0
    price_lo = int(price * 0.7) if price else 0
    price_hi = int(price * 1.3) if price else 999999

    query = (
        select(Vehicle)
        .where(
            Vehicle.vin != vehicle.vin,
            Vehicle.available == True,  # noqa: E712
            func.lower(Vehicle.make) == (vehicle.make or "").lower(),
            Vehicle.year >= (vehicle.year or 2020) - 3,
            Vehicle.year <= (vehicle.year or 2020) + 3,
            Vehicle.price_asking >= price_lo,
            Vehicle.price_asking <= price_hi,
        )
        .order_by(
            # Prefer same model first
            case((func.lower(Vehicle.model) == (vehicle.model or "").lower(), 0), else_=1),
            Vehicle.updated_at.desc(),
        )
        .limit(limit)
    )
    rows = db.scalars(query).all()

    results = []
    for row in rows:
        card_media = resolve_vehicle_card_media(db, vehicle=row)
        hero = card_media.thumbnail or (None if card_media.dealer_photos_gated else (row.images[0] if row.images else None))
        normalized = row.features_normalized or {}
        results.append({
            "vin": row.vin,
            "public_slug": row.public_slug,
            "year": row.year,
            "make": row.make,
            "model": row.model,
            "trim": row.trim,
            "body_type": row.body_type,
            "price_asking": _pricing_breakdown(row.price_asking)["advertised_price"],
            "odometer": row.odometer,
            "location_state": row.location_state,
            "location_zip": row.location_zip,
            "exterior_color": normalized.get("exterior_color"),
            "interior_color": normalized.get("interior_color"),
            "source_type": row.source_type,
            "source_label": _public_source_label(row.source_type),
            "hero_image": hero,
            "has_images": bool(row.images),
            "badges": _compute_badges(
                row.year, row.odometer, row.price_asking,
                _normalized_pick(normalized, "mmr", "mmr_value", "manheim_mmr"),
            ),
        })

    return ok(results)
