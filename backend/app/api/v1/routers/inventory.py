import csv
import io
import re
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import asc, desc, func, or_, select
from sqlalchemy.orm import Session

from app.api.deps import require_service_token
from app.core.config import settings
from app.core.responses import ok
from app.db.session import get_db
from app.integrations.marketcheck_client import MarketCheckClient
from app.models.entities import Vehicle
from app.services.image_pipeline_service import resolve_vehicle_card_media, resolve_vehicle_display_context
from app.services.inventory_service import SOURCE_PRIORITY, ingest_marketcheck_inventory, seed_inventory

router = APIRouter()

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

WORDPRESS_EXPORT_COLUMNS = [
    "external_id",
    "vin",
    "title",
    "slug",
    "year",
    "make",
    "model",
    "trim",
    "body_type",
    "drivetrain",
    "fuel_type",
    "transmission",
    "mileage",
    "price",
    "condition_grade",
    "inventory_type",
    "certified",
    "single_owner",
    "clean_title",
    "days_on_market",
    "exterior_color",
    "interior_color",
    "city",
    "state",
    "zip",
    "dealer_name",
    "source_type",
    "source_priority",
    "source_url",
    "thumbnail",
    "image_count",
    "image_display_mode",
    "inspection_status",
    "has_inspection_report",
    "photos_coming_soon",
    "image_urls",
    "features",
    "description",
    "marketcheck_average_retail",
    "price_delta_marketcheck",
    "price_delta_marketcheck_pct",
    "vdp_path",
    "vdp_url",
    "available",
    "updated_at",
    "last_seen_active",
]

SLUG_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")


def _marketcheck_client() -> MarketCheckClient:
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


def _to_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_feature_list(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = _to_str(value)
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(text)
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


def _build_vehicle_title(vehicle: Vehicle) -> str:
    parts = [str(vehicle.year), vehicle.make, vehicle.model]
    trim = _to_str(vehicle.trim)
    if trim:
        parts.append(trim)
    return " ".join([part for part in parts if part]).strip()


def _build_vehicle_slug(vehicle: Vehicle) -> str:
    parts = [
        _normalize_slug_part(vehicle.year),
        _normalize_slug_part(vehicle.make),
        _normalize_slug_part(vehicle.model),
        _normalize_slug_part(vehicle.trim),
        _normalize_slug_part(vehicle.vin),
    ]
    filtered = [part for part in parts if part]
    return "-".join(filtered) or vehicle.vin.lower()


def _build_vdp_links(vin: str) -> tuple[str, str]:
    path = f"/vinventory-details.html?vin={vin}"
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


def _serialize_wordpress_vehicle(db: Session, vehicle: Vehicle) -> dict[str, Any]:
    display_context = resolve_vehicle_display_context(db, vehicle=vehicle)
    gallery = display_context.get("gallery_images") or vehicle.images or []
    hero_image = display_context.get("hero_image")
    normalized = vehicle.features_normalized or {}

    image_urls = _dedupe_strings([hero_image, *[str(value) for value in gallery]])
    features = _normalize_feature_list(vehicle.features_raw or [])
    source_name = (vehicle.source_type or "").lower()
    source_priority = SOURCE_PRIORITY.get(source_name, 0)
    vdp_path, vdp_url = _build_vdp_links(vehicle.vin)

    return {
        "external_id": vehicle.vin,
        "vin": vehicle.vin,
        "title": _build_vehicle_title(vehicle),
        "slug": _build_vehicle_slug(vehicle),
        "year": vehicle.year,
        "make": vehicle.make,
        "model": vehicle.model,
        "trim": vehicle.trim,
        "body_type": vehicle.body_type,
        "drivetrain": vehicle.drivetrain,
        "fuel_type": normalized.get("fuel_type"),
        "transmission": normalized.get("transmission"),
        "mileage": vehicle.odometer,
        "price": vehicle.price_asking,
        "condition_grade": vehicle.condition_grade,
        "inventory_type": normalized.get("inventory_type"),
        "certified": normalized.get("certified"),
        "single_owner": normalized.get("single_owner"),
        "clean_title": normalized.get("clean_title"),
        "days_on_market": normalized.get("days_on_market"),
        "exterior_color": normalized.get("exterior_color"),
        "interior_color": normalized.get("interior_color"),
        "city": normalized.get("city"),
        "state": vehicle.location_state,
        "zip": vehicle.location_zip,
        "dealer_name": normalized.get("dealer_name"),
        "source_type": vehicle.source_type,
        "source_priority": source_priority,
        "source_url": vehicle.source_url,
        "thumbnail": image_urls[0] if image_urls else None,
        "image_count": len(image_urls),
        "image_display_mode": display_context.get("mode"),
        "inspection_status": display_context.get("inspection_status"),
        "has_inspection_report": bool(display_context.get("has_inspection_report")),
        "photos_coming_soon": len(image_urls) == 0,
        "images": image_urls,
        "features": features,
        "description": normalized.get("description"),
        "marketcheck_average_retail": None,
        "price_delta_marketcheck": None,
        "price_delta_marketcheck_pct": None,
        "vdp_path": vdp_path,
        "vdp_url": vdp_url,
        "available": vehicle.available,
        "updated_at": _to_iso(vehicle.updated_at),
        "last_seen_active": _to_iso(vehicle.last_seen_active),
    }


def _extract_marketcheck_average_retail(payload: Any) -> float | None:
    if not isinstance(payload, dict):
        return None

    candidates: list[Any] = [
        payload.get("average_retail"),
        payload.get("avg_price"),
        payload.get("average"),
        payload.get("market_price"),
        payload.get("retail"),
        payload.get("estimated_market_price"),
    ]

    prices = payload.get("prices")
    if isinstance(prices, dict):
        candidates.extend(
            [
                prices.get("average_retail"),
                prices.get("avg_price"),
                prices.get("average"),
                prices.get("retail"),
                prices.get("market_price"),
            ]
        )

    market = payload.get("market")
    if isinstance(market, dict):
        candidates.extend(
            [
                market.get("average_retail"),
                market.get("avg_price"),
                market.get("average"),
                market.get("retail"),
                market.get("market_price"),
            ]
        )

    listings = payload.get("listings")
    if isinstance(listings, list):
        listing_prices = [_to_float(row.get("price")) for row in listings if isinstance(row, dict)]
        numeric_prices = [value for value in listing_prices if value is not None]
        if numeric_prices:
            candidates.append(round(sum(numeric_prices) / len(numeric_prices), 2))

    for candidate in candidates:
        parsed = _to_float(candidate)
        if parsed is not None and parsed > 0:
            return round(parsed, 2)

    return None


def _attach_marketcheck_price_stats(client: MarketCheckClient, items: list[dict[str, Any]]) -> None:
    for item in items:
        vin = _to_str(item.get("vin"))
        asking_price = _to_float(item.get("price"))

        item["marketcheck_average_retail"] = None
        item["price_delta_marketcheck"] = None
        item["price_delta_marketcheck_pct"] = None

        if not vin:
            continue

        try:
            stats = client.get_price(vin)
        except Exception:
            continue

        market_retail = _extract_marketcheck_average_retail(stats)
        if market_retail is None:
            continue

        item["marketcheck_average_retail"] = market_retail

        if asking_price is None or asking_price <= 0:
            continue

        delta = round(market_retail - asking_price, 2)
        item["price_delta_marketcheck"] = delta
        item["price_delta_marketcheck_pct"] = round((delta / market_retail) * 100, 2) if market_retail else None


def _to_csv_bool(value: Any) -> str:
    parsed = _to_bool(value)
    if parsed is None:
        return ""
    return "1" if parsed else "0"


def _serialize_wordpress_csv_row(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "external_id": item.get("external_id") or "",
        "vin": item.get("vin") or "",
        "title": item.get("title") or "",
        "slug": item.get("slug") or "",
        "year": item.get("year") or "",
        "make": item.get("make") or "",
        "model": item.get("model") or "",
        "trim": item.get("trim") or "",
        "body_type": item.get("body_type") or "",
        "drivetrain": item.get("drivetrain") or "",
        "fuel_type": item.get("fuel_type") or "",
        "transmission": item.get("transmission") or "",
        "mileage": item.get("mileage") or "",
        "price": item.get("price") or "",
        "condition_grade": item.get("condition_grade") or "",
        "inventory_type": item.get("inventory_type") or "",
        "certified": _to_csv_bool(item.get("certified")),
        "single_owner": _to_csv_bool(item.get("single_owner")),
        "clean_title": _to_csv_bool(item.get("clean_title")),
        "days_on_market": item.get("days_on_market") or "",
        "exterior_color": item.get("exterior_color") or "",
        "interior_color": item.get("interior_color") or "",
        "city": item.get("city") or "",
        "state": item.get("state") or "",
        "zip": item.get("zip") or "",
        "dealer_name": item.get("dealer_name") or "",
        "source_type": item.get("source_type") or "",
        "source_priority": item.get("source_priority") or 0,
        "source_url": item.get("source_url") or "",
        "thumbnail": item.get("thumbnail") or "",
        "image_count": item.get("image_count") or 0,
        "image_display_mode": item.get("image_display_mode") or "",
        "inspection_status": item.get("inspection_status") or "",
        "has_inspection_report": _to_csv_bool(item.get("has_inspection_report")),
        "photos_coming_soon": _to_csv_bool(item.get("photos_coming_soon")),
        "image_urls": "|".join(item.get("images") or []),
        "features": "|".join(item.get("features") or []),
        "description": item.get("description") or "",
        "marketcheck_average_retail": item.get("marketcheck_average_retail") or "",
        "price_delta_marketcheck": item.get("price_delta_marketcheck") or "",
        "price_delta_marketcheck_pct": item.get("price_delta_marketcheck_pct") or "",
        "vdp_path": item.get("vdp_path") or "",
        "vdp_url": item.get("vdp_url") or "",
        "available": _to_csv_bool(item.get("available")),
        "updated_at": item.get("updated_at") or "",
        "last_seen_active": item.get("last_seen_active") or "",
    }


def _build_wordpress_export_csv(items: list[dict[str, Any]]) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=WORDPRESS_EXPORT_COLUMNS)
    writer.writeheader()
    for item in items:
        writer.writerow(_serialize_wordpress_csv_row(item))
    return buffer.getvalue()


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
) -> dict[str, Any]:
    params: dict[str, Any] = {
        "make": make,
        "model": model,
        "trim": trim,
        "body_type": body_type,
        "car_type": body_type,
        "state": state.upper() if state else None,
        "exterior_color": exterior_color,
        "interior_color": interior_color,
        "drivetrain": drivetrain,
        "fuel_type": fuel_type,
        "transmission": transmission,
        "inventory_type": inventory_type,
        "vin": q.strip().upper() if q and len(q.strip()) == 17 else None,
        "has_photo": has_images if has_images is True else None,
        "certified": str(certified).lower() if certified is not None else None,
        "carfax_1_owner": str(single_owner).lower() if single_owner is not None else None,
        "carfax_clean_title": str(clean_title).lower() if clean_title is not None else None,
    }

    if min_price is not None and max_price is not None:
        params["price_range"] = f"{int(min_price)}-{int(max_price)}"
    if min_year is not None and max_year is not None:
        if min_year == max_year:
            params["year"] = min_year
        else:
            params["year_range"] = f"{min_year}-{max_year}"
    if min_dom is not None and max_dom is not None:
        params["dom_range"] = f"{min_dom}-{max_dom}"

    return {k: v for k, v in params.items() if v not in (None, "")}


def _extract_listing_metadata(listing: dict[str, Any] | None) -> dict[str, Any]:
    listing = listing or {}
    build = listing.get("build") if isinstance(listing.get("build"), dict) else {}
    extra = listing.get("extra") if isinstance(listing.get("extra"), dict) else {}
    dealer = listing.get("dealer") if isinstance(listing.get("dealer"), dict) else {}

    features = _normalize_feature_list(extra.get("features") or listing.get("features") or [])
    high_value = _normalize_feature_list(extra.get("high_value_features") or [])
    options = _normalize_feature_list(extra.get("options") or [])

    merged_features: list[str] = []
    seen: set[str] = set()
    for source in (features, high_value, options):
        for value in source:
            key = value.lower()
            if key in seen:
                continue
            seen.add(key)
            merged_features.append(value)

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
        "dealer_name": _to_str(dealer.get("name") or listing.get("mc_dealership") or listing.get("heading")),
        "city": _to_str(dealer.get("city") or listing.get("city")),
        "features": merged_features,
        "high_value_features": high_value,
        "options": options,
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


def _local_facets(db: Session, *, make: str | None, model: str | None, state: str | None, body_type: str | None) -> dict[str, Any]:
    stmt = select(Vehicle).where(Vehicle.available.is_(True))
    if make:
        stmt = stmt.where(func.lower(Vehicle.make) == make.lower())
    if model:
        stmt = stmt.where(func.lower(Vehicle.model) == model.lower())
    if state:
        stmt = stmt.where(func.lower(Vehicle.location_state) == state.lower())
    if body_type:
        stmt = stmt.where(func.lower(Vehicle.body_type) == body_type.lower())

    rows = db.scalars(stmt.limit(5000)).all()

    facets: dict[str, dict[str, int]] = {name: {} for name in FACET_FIELDS}
    for row in rows:
        def add(name: str, value: str | None) -> None:
            text = _to_str(value)
            if not text:
                return
            facets[name][text] = facets[name].get(text, 0) + 1

        normalized = row.features_normalized or {}
        add("make", row.make)
        add("model", row.model)
        add("trim", row.trim)
        add("body_type", row.body_type)
        add("state", row.location_state)
        add("city", normalized.get("city"))
        add("exterior_color", normalized.get("exterior_color"))
        add("interior_color", normalized.get("interior_color"))
        add("drivetrain", row.drivetrain)
        add("fuel_type", normalized.get("fuel_type"))
        add("transmission", normalized.get("transmission"))
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
    make: str | None = Query(default=None),
    model: str | None = Query(default=None),
    body_type: str | None = Query(default=None),
    state: str | None = Query(default=None, min_length=2, max_length=2),
    inventory_type: str | None = Query(default=None),
    min_price: float | None = Query(default=None),
    max_price: float | None = Query(default=None),
    min_year: int | None = Query(default=None),
    max_year: int | None = Query(default=None),
    has_images: bool | None = Query(default=True),
    use_marketcheck: bool = Query(default=True),
    db: Session = Depends(get_db),
) -> dict:
    if use_marketcheck and settings.has_marketcheck:
        client = _marketcheck_client()
        params = _build_marketcheck_search_params(
            q=None,
            make=make,
            model=model,
            trim=None,
            body_type=body_type,
            state=state,
            min_price=min_price,
            max_price=max_price,
            min_year=min_year,
            max_year=max_year,
            has_images=has_images,
            exterior_color=None,
            interior_color=None,
            drivetrain=None,
            fuel_type=None,
            transmission=None,
            inventory_type=inventory_type,
            certified=None,
            single_owner=None,
            clean_title=None,
            min_dom=None,
            max_dom=None,
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
                }
            )
        except Exception:
            pass

    return ok({"source": "local", "num_found": 0, "facets": _local_facets(db, make=make, model=model, state=state, body_type=body_type)})


@router.get("/search")
def search_inventory(
    q: str | None = Query(default=None),
    make: str | None = Query(default=None),
    model: str | None = Query(default=None),
    trim: str | None = Query(default=None),
    body_type: str | None = Query(default=None),
    source_type: str | None = Query(default=None),
    state: str | None = Query(default=None, min_length=2, max_length=2),
    exterior_color: str | None = Query(default=None),
    interior_color: str | None = Query(default=None),
    drivetrain: str | None = Query(default=None),
    fuel_type: str | None = Query(default=None),
    transmission: str | None = Query(default=None),
    inventory_type: str | None = Query(default=None),
    certified: bool | None = Query(default=None),
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
    has_images: bool | None = Query(default=None),
    sort_by: str = Query(default="updated_at", pattern="^(updated_at|price_asking|year|odometer)$"),
    sort_dir: str = Query(default="desc", pattern="^(asc|desc)$"),
    live_sync: bool = Query(default=False),
    sync_limit: int = Query(default=72, ge=1, le=300),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=24, ge=1, le=100),
    db: Session = Depends(get_db),
) -> dict:
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
    synced_vins: list[str] = []

    if live_sync and settings.marketcheck_api_key:
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
            min_dom=min_dom,
            max_dom=max_dom,
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
            synced_vins = report_data.get("synced_vins", [])
        except Exception as exc:  # pragma: no cover - integration failures are environment dependent
            db.rollback()
            sync.update(
                {
                    "executed": True,
                    "mode": "error",
                    "error": str(exc),
                }
            )

    stmt = select(Vehicle).where(Vehicle.available.is_(True))
    if synced_vins:
        stmt = stmt.where(Vehicle.vin.in_(synced_vins))

    if q:
        text = f"%{q.lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(Vehicle.vin).like(text),
                func.lower(Vehicle.make).like(text),
                func.lower(Vehicle.model).like(text),
                func.lower(func.coalesce(Vehicle.trim, "")).like(text),
            )
        )
    if make:
        stmt = stmt.where(func.lower(Vehicle.make) == make.lower())
    if model:
        stmt = stmt.where(func.lower(Vehicle.model) == model.lower())
    if trim:
        stmt = stmt.where(func.lower(func.coalesce(Vehicle.trim, "")) == trim.lower())
    if body_type:
        stmt = stmt.where(func.lower(Vehicle.body_type) == body_type.lower())
    if source_type:
        stmt = stmt.where(func.lower(Vehicle.source_type) == source_type.lower())
    if state:
        stmt = stmt.where(func.lower(Vehicle.location_state) == state.lower())
    if drivetrain:
        stmt = stmt.where(func.lower(func.coalesce(Vehicle.drivetrain, "")) == drivetrain.lower())
    if min_price is not None:
        stmt = stmt.where(Vehicle.price_asking >= min_price)
    if max_price is not None:
        stmt = stmt.where(Vehicle.price_asking <= max_price)
    if min_year is not None:
        stmt = stmt.where(Vehicle.year >= min_year)
    if max_year is not None:
        stmt = stmt.where(Vehicle.year <= max_year)
    if min_miles is not None:
        stmt = stmt.where(Vehicle.odometer >= min_miles)
    if max_miles is not None:
        stmt = stmt.where(Vehicle.odometer <= max_miles)
    if has_images is True:
        stmt = stmt.where(func.coalesce(func.json_array_length(Vehicle.images), 0) > 0)

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0

    sort_columns = {
        "updated_at": Vehicle.updated_at,
        "price_asking": Vehicle.price_asking,
        "year": Vehicle.year,
        "odometer": Vehicle.odometer,
    }
    order_column = sort_columns[sort_by]
    order_by = asc(order_column) if sort_dir == "asc" else desc(order_column)

    offset = (page - 1) * per_page
    rows = db.scalars(stmt.order_by(order_by).offset(offset).limit(per_page)).all()

    total_pages = max(1, (total + per_page - 1) // per_page) if total else 0

    items: list[dict[str, Any]] = []
    for row in rows:
        media = resolve_vehicle_card_media(db, vehicle=row)
        normalized = row.features_normalized or {}
        items.append(
            {
                "vin": row.vin,
                "listing_id": row.listing_id,
                "year": row.year,
                "make": row.make,
                "model": row.model,
                "trim": row.trim,
                "body_type": row.body_type,
                "drivetrain": row.drivetrain,
                "price_asking": row.price_asking,
                "odometer": row.odometer,
                "location_state": row.location_state,
                "location_zip": row.location_zip,
                "source_type": row.source_type,
                "thumbnail": media.thumbnail,
                "images_count": len(row.images or []),
                "features_preview": (row.features_raw or [])[:5],
                "display_mode": media.display_mode.value,
                "inspection_status": media.inspection_status.value,
                "has_inspection_report": media.has_inspection_report,
                "exterior_color": normalized.get("exterior_color"),
                "interior_color": normalized.get("interior_color"),
                "fuel_type": normalized.get("fuel_type"),
                "transmission": normalized.get("transmission"),
                "inventory_type": normalized.get("inventory_type"),
                "days_on_market": normalized.get("days_on_market"),
                "single_owner": normalized.get("single_owner"),
                "clean_title": normalized.get("clean_title"),
                "certified": normalized.get("certified"),
                "dealer_name": normalized.get("dealer_name"),
                "city": normalized.get("city"),
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


@router.get("/wordpress/export", response_model=None)
def wordpress_inventory_export(
    format: str = Query(default="json", pattern="^(json|csv)$"),
    q: str | None = Query(default=None),
    make: str | None = Query(default=None),
    model: str | None = Query(default=None),
    trim: str | None = Query(default=None),
    body_type: str | None = Query(default=None),
    source_type: str | None = Query(default=None),
    state: str | None = Query(default=None, min_length=2, max_length=2),
    min_price: float | None = Query(default=None),
    max_price: float | None = Query(default=None),
    min_year: int | None = Query(default=None),
    max_year: int | None = Query(default=None),
    has_images: bool | None = Query(default=None),
    include_unavailable: bool = Query(default=False),
    updated_since: str | None = Query(default=None),
    include_price_stats: bool = Query(default=False),
    sort_by: str = Query(default="updated_at", pattern="^(updated_at|price|year|mileage)$"),
    sort_dir: str = Query(default="desc", pattern="^(asc|desc)$"),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
) -> Any:
    updated_since_at = _parse_iso8601(updated_since)
    if updated_since and updated_since_at is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="updated_since must be a valid ISO-8601 timestamp",
        )

    stmt = select(Vehicle)
    if not include_unavailable:
        stmt = stmt.where(Vehicle.available.is_(True))

    if q:
        text = f"%{q.lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(Vehicle.vin).like(text),
                func.lower(Vehicle.make).like(text),
                func.lower(Vehicle.model).like(text),
                func.lower(func.coalesce(Vehicle.trim, "")).like(text),
            )
        )
    if make:
        stmt = stmt.where(func.lower(Vehicle.make) == make.lower())
    if model:
        stmt = stmt.where(func.lower(Vehicle.model) == model.lower())
    if trim:
        stmt = stmt.where(func.lower(func.coalesce(Vehicle.trim, "")) == trim.lower())
    if body_type:
        stmt = stmt.where(func.lower(Vehicle.body_type) == body_type.lower())
    if source_type:
        stmt = stmt.where(func.lower(Vehicle.source_type) == source_type.lower())
    if state:
        stmt = stmt.where(func.lower(Vehicle.location_state) == state.lower())
    if min_price is not None:
        stmt = stmt.where(Vehicle.price_asking >= min_price)
    if max_price is not None:
        stmt = stmt.where(Vehicle.price_asking <= max_price)
    if min_year is not None:
        stmt = stmt.where(Vehicle.year >= min_year)
    if max_year is not None:
        stmt = stmt.where(Vehicle.year <= max_year)
    if has_images is True:
        stmt = stmt.where(func.coalesce(func.json_array_length(Vehicle.images), 0) > 0)
    if updated_since_at is not None:
        stmt = stmt.where(Vehicle.updated_at >= updated_since_at)

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0

    sort_columns = {
        "updated_at": Vehicle.updated_at,
        "price": Vehicle.price_asking,
        "year": Vehicle.year,
        "mileage": Vehicle.odometer,
    }
    order_column = sort_columns[sort_by]
    order_by = asc(order_column) if sort_dir == "asc" else desc(order_column)

    offset = (page - 1) * per_page
    rows = db.scalars(
        stmt.order_by(order_by, desc(Vehicle.updated_at), asc(Vehicle.vin)).offset(offset).limit(per_page)
    ).all()
    items = [_serialize_wordpress_vehicle(db, row) for row in rows]
    price_stats_enriched = False

    if include_price_stats and settings.has_marketcheck and items:
        try:
            _attach_marketcheck_price_stats(_marketcheck_client(), items)
            price_stats_enriched = True
        except Exception:
            price_stats_enriched = False

    total_pages = max(1, (total + per_page - 1) // per_page) if total else 0
    payload = {
        "items": items,
        "pagination": {
            "page": page,
            "per_page": per_page,
            "total": total,
            "total_pages": total_pages,
            "has_next": page < total_pages,
            "has_prev": page > 1 and total_pages > 0,
        },
        "export": {
            "format": format,
            "generated_at": _to_iso(datetime.now(UTC)),
            "source_priority": SOURCE_PRIORITY,
            "price_stats": {
                "requested": include_price_stats,
                "enabled": bool(settings.has_marketcheck),
                "enriched": price_stats_enriched,
            },
        },
    }

    if format == "json":
        return ok(payload)

    filename = datetime.now(UTC).strftime("virtualcarhub-inventory-%Y%m%dT%H%M%SZ.csv")
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return Response(
        content=_build_wordpress_export_csv(items),
        media_type="text/csv; charset=utf-8",
        headers=headers,
    )


@router.get("/{vin}")
def get_inventory_vehicle(vin: str, db: Session = Depends(get_db)) -> dict:
    vehicle = db.get(Vehicle, vin.upper())
    if not vehicle:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Vehicle not found")

    display_context = resolve_vehicle_display_context(db, vehicle=vehicle)
    resolved_images = display_context.get("gallery_images") or (vehicle.images or [])
    hero_image = display_context.get("hero_image") or (resolved_images[0] if resolved_images else None)

    listing_meta: dict[str, Any] = {}
    if settings.has_marketcheck and vehicle.source_type == "marketcheck":
        try:
            listing = _fetch_marketcheck_listing_by_vehicle(_marketcheck_client(), vehicle)
            listing_meta = _extract_listing_metadata(listing)
        except Exception:
            listing_meta = {}

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

    return ok(
        {
            "vin": vehicle.vin,
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
            "price_asking": vehicle.price_asking,
            "price_wholesale_est": vehicle.price_wholesale_est,
            "location_zip": vehicle.location_zip,
            "location_state": vehicle.location_state,
            "source_type": vehicle.source_type,
            "images": vehicle.images or [],
            "display_images": resolved_images,
            "hero_image": hero_image,
            "display_mode": display_context.get("mode"),
            "inspection_status": display_context.get("inspection_status"),
            "has_inspection_report": bool(display_context.get("has_inspection_report")),
            "features_raw": merged_features,
            "features_full": merged_features,
            "high_value_features": listing_meta.get("high_value_features") or [],
            "options": listing_meta.get("options") or [],
            "description": listing_meta.get("description"),
            "exterior_color": listing_meta.get("exterior_color") or normalized.get("exterior_color"),
            "interior_color": listing_meta.get("interior_color") or normalized.get("interior_color"),
            "fuel_type": listing_meta.get("fuel_type") or normalized.get("fuel_type"),
            "transmission": listing_meta.get("transmission") or normalized.get("transmission"),
            "inventory_type": listing_meta.get("inventory_type") or normalized.get("inventory_type"),
            "days_on_market": listing_meta.get("days_on_market") or normalized.get("days_on_market"),
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
            "available": vehicle.available,
            "last_seen_active": vehicle.last_seen_active,
            "updated_at": vehicle.updated_at,
            "display_context": display_context,
        }
    )
