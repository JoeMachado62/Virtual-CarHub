from __future__ import annotations

import csv
import io
import logging
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.constants import AuctionPlatform, ImageContext, ImageJobStatus, ImageTier
from app.integrations.evox_client import EvoxClient
from app.models.entities import EvoxColorCache, EvoxVifCache, Vehicle, VehicleImageAsset

logger = logging.getLogger(__name__)

EVOX_SOURCE_KIND = "evox"

# ---- Product Type IDs (from EVOX spec guide) ----

# Card-level: 3-angle color, 1280x960, JPEG (Product ID 70)
PTID_COLOR_SIDE_1280 = 786      # frame 01, side profile
PTID_COLOR_REAR34_1280 = 787    # frame 14, rear 3/4
PTID_COLOR_FRONT34_1280 = 788   # frame 32, front 3/4

# Detail-level: stills on grey stage (Product ID 80)
PTID_STILLS_GREY_480 = 873      # 480x360 JPEG
PTID_STILLS_GREY_1280 = 876     # 1280x960 PNG transparent

# Detail-level: stills on white background (Product ID 80)
PTID_STILLS_WHITE_640 = 882     # 640x480 JPEG
PTID_STILLS_WHITE_1280 = 883    # 1280x960 JPEG

# Exterior spinframes: 36-frame colorized (Product ID 73)
PTID_EXT_COLOR_SPIN_1280 = 831  # 1280x960, 36 frames, colorized JPEG

# Interior: equirectangular panorama (Product ID 77)
PTID_INTERIOR_EQ_4000 = 862     # 4000x2000 PNG

# Card-level PTIDs (always requested for hero/gallery)
CARD_PTIDS = [PTID_COLOR_SIDE_1280, PTID_COLOR_REAR34_1280, PTID_COLOR_FRONT34_1280]

# Detail-level PTIDs — ORDERING IS CRITICAL:
# Rich products (stills, interior, spin) MUST come before 3-angle color.
# If 3AC PTIDs are listed first, the API may skip vehicles with richer assets.
# This ordering forces a match to the richest available library tier.
DETAIL_PTIDS = [
    # Stills — white background, 1280x960 JPEG (best resolution; grey stage and
    # smaller variants are the same shots at lower quality, so skip them)
    PTID_STILLS_WHITE_1280,
    # Interior panorama (AIL tier only)
    PTID_INTERIOR_EQ_4000,
    # Exterior colorized spin (CG/AIL tiers)
    PTID_EXT_COLOR_SPIN_1280,
    # 3-angle color (all tiers — listed LAST per EVOX ordering rule)
    PTID_COLOR_SIDE_1280,
    PTID_COLOR_REAR34_1280,
    PTID_COLOR_FRONT34_1280,
]

# Map PTIDs to asset roles for response parsing
_PTID_ROLE_MAP: dict[int, str] = {
    PTID_COLOR_SIDE_1280: "hero",
    PTID_COLOR_REAR34_1280: "gallery",
    PTID_COLOR_FRONT34_1280: "gallery",
    PTID_STILLS_GREY_480: "exterior_still",
    PTID_STILLS_GREY_1280: "exterior_still",
    PTID_STILLS_WHITE_640: "exterior_still",
    PTID_STILLS_WHITE_1280: "exterior_still",
    PTID_EXT_COLOR_SPIN_1280: "spin",
    PTID_INTERIOR_EQ_4000: "interior_pano",
}


# ---- Data classes ----

@dataclass(slots=True)
class EvoxColorInfo:
    """Color info extracted from EVOX API response (no separate lookup needed)."""
    color_code: str
    color_title: str
    color_simpletitle: str
    is_exact_match: bool  # True if simpletitle matches vehicle's exterior_color
    match_source: str     # "response_match" | "response_default"


@dataclass(slots=True)
class EvoxManifest:
    vin: str
    vifid: int
    color_info: EvoxColorInfo | None
    match_level: str  # "trim" or "model"
    hero_url: str
    card_gallery_urls: list[str]
    exterior_stills: list[str] = field(default_factory=list)
    interior_stills: list[str] = field(default_factory=list)
    spin_urls: list[str] = field(default_factory=list)
    interior_pano_url: str | None = None
    vif_data: dict = field(default_factory=dict)
    available_products: dict = field(default_factory=dict)


# ---- Client singleton ----

_client: EvoxClient | None = None


def _get_client() -> EvoxClient:
    global _client
    if _client is None:
        _client = EvoxClient(
            api_key=settings.evox_api_key,
            api_base_url=settings.evox_api_base_url,
            live=settings.has_evox,
        )
    return _client


# ---- VIN-direct manifest building ----

def _build_ymmt_request(vehicle: Vehicle) -> dict[str, Any] | None:
    """Build a YMMT query dict for EVOX fallback when VIN lookup fails."""
    if not vehicle.year or not vehicle.make or not vehicle.model:
        return None
    req: dict[str, Any] = {
        "year": vehicle.year,
        "make": vehicle.make,
        "model": vehicle.model,
    }
    if vehicle.trim:
        req["trim"] = vehicle.trim
    return req


def build_evox_manifest(
    vehicle: Vehicle,
    *,
    detail_level: str = "card",
) -> EvoxManifest | None:
    """Build an EVOX image manifest for a single vehicle.

    Tries VIN-direct query first for factory paint accuracy.
    Falls back to YMMT query if VIN returns no match.
    """
    if not settings.has_evox:
        return None
    if not vehicle.vin and not (vehicle.year and vehicle.make and vehicle.model):
        return None

    ptids = CARD_PTIDS if detail_level == "card" else DETAIL_PTIDS

    client = _get_client()

    # Step 1: Try VIN-direct query
    if vehicle.vin:
        try:
            response = client.batch_product_query(
                [{"vin": vehicle.vin}],
                ptids,
                webp=settings.evox_prefer_webp,
            )
        except Exception:
            logger.warning("EVOX VIN query failed for vin=%s", vehicle.vin, exc_info=True)
            response = None

        if response and response.get("source") != "stub":
            query_responses = response.get("query_responses", [])
            if query_responses:
                manifest = _parse_response_item(vehicle, query_responses[0], detail_level)
                if manifest:
                    return manifest

    # Step 2: Fallback to YMMT query
    ymmt_req = _build_ymmt_request(vehicle)
    if not ymmt_req:
        return None

    try:
        response = client.batch_product_query(
            [ymmt_req],
            ptids,
            webp=settings.evox_prefer_webp,
        )
    except Exception:
        logger.warning("EVOX YMMT query failed for %s %s %s", vehicle.year, vehicle.make, vehicle.model, exc_info=True)
        return None

    if response.get("source") == "stub":
        return None

    query_responses = response.get("query_responses", [])
    if not query_responses:
        return None

    return _parse_response_item(vehicle, query_responses[0], detail_level)


def batch_build_evox_manifests(
    vehicles: list[Vehicle],
    *,
    detail_level: str = "card",
) -> dict[str, EvoxManifest]:
    """Build EVOX manifests for multiple vehicles in batched API calls (max 10 per call).

    Tries VIN-direct queries first, then falls back to YMMT for any misses.
    Returns a dict mapping VIN → EvoxManifest for vehicles that had EVOX matches.
    """
    if not settings.has_evox or not vehicles:
        return {}

    ptids = CARD_PTIDS if detail_level == "card" else DETAIL_PTIDS
    client = _get_client()
    results: dict[str, EvoxManifest] = {}

    # Step 1: Batch VIN-direct queries (groups of 10)
    for i in range(0, len(vehicles), 10):
        batch = vehicles[i:i + 10]
        requests = [{"vin": v.vin} for v in batch if v.vin]
        if not requests:
            continue

        try:
            response = client.batch_product_query(
                requests,
                ptids,
                webp=settings.evox_prefer_webp,
            )
        except Exception:
            logger.warning(
                "EVOX VIN batch query failed for batch of %d vehicles",
                len(requests),
                exc_info=True,
            )
            continue

        if response.get("source") == "stub":
            continue

        query_responses = response.get("query_responses", [])
        for vehicle, resp_item in zip(batch, query_responses):
            manifest = _parse_response_item(vehicle, resp_item, detail_level)
            if manifest:
                results[vehicle.vin] = manifest

    # Step 2: YMMT fallback for vehicles that had no VIN match
    missed = [v for v in vehicles if v.vin not in results]
    if not missed:
        return results

    # Deduplicate by YMMT — vehicles with the same YMMT share one query slot
    ymmt_groups: dict[tuple, list[Vehicle]] = {}
    for v in missed:
        ymmt_req = _build_ymmt_request(v)
        if not ymmt_req:
            continue
        key = (v.year, v.make.lower(), v.model.lower(), (v.trim or "").lower())
        ymmt_groups.setdefault(key, []).append(v)

    unique_ymmt_reqs = []
    ymmt_keys_ordered = []
    for key, group in ymmt_groups.items():
        ymmt_keys_ordered.append(key)
        unique_ymmt_reqs.append(_build_ymmt_request(group[0]))

    for i in range(0, len(unique_ymmt_reqs), 10):
        batch_reqs = unique_ymmt_reqs[i:i + 10]
        batch_keys = ymmt_keys_ordered[i:i + 10]

        try:
            response = client.batch_product_query(
                batch_reqs,
                ptids,
                webp=settings.evox_prefer_webp,
            )
        except Exception:
            logger.warning("EVOX YMMT batch query failed for %d groups", len(batch_reqs), exc_info=True)
            continue

        if response.get("source") == "stub":
            continue

        query_responses = response.get("query_responses", [])
        for key, resp_item in zip(batch_keys, query_responses):
            if not (resp_item.get("product_types") or {}):
                continue
            # Parse per-vehicle so each gets its own color match
            for v in ymmt_groups[key]:
                manifest = _parse_response_item(v, resp_item, detail_level)
                if manifest:
                    results[v.vin] = manifest

    return results


def _pick_best_color_code(items: list[dict[str, Any]], vehicle: Vehicle) -> str | None:
    """Pick the best color_code from a multi-color EVOX response.

    Matches against the vehicle's exterior_color (from features_normalized).
    Returns the color_code to filter on, or None to take the first available.
    """
    if not items or len(items) <= 1:
        return None  # Single color or empty — no filtering needed

    normalized = vehicle.features_normalized or {}
    ext_color = (normalized.get("exterior_color") or "").strip().lower()
    if not ext_color:
        return None  # No color info on vehicle — take default (first)

    # Collect unique color codes with their simpletitles and full titles
    seen: dict[str, dict[str, str]] = {}
    for item in items:
        cc = item.get("color_code", "")
        if cc and cc not in seen:
            seen[cc] = {
                "simpletitle": (item.get("color_simpletitle") or "").lower(),
                "title": (item.get("color_title") or "").lower(),
            }

    # Try exact simpletitle match first (e.g. "white" == "white")
    for cc, info in seen.items():
        if info["simpletitle"] == ext_color:
            return cc

    # Try partial match on full title (e.g. "star white" in "star white metallic tri-coat")
    for cc, info in seen.items():
        if ext_color in info["title"] or info["simpletitle"] in ext_color:
            return cc

    return None  # No match — caller takes first image per PTID


def _parse_response_item(
    vehicle: Vehicle,
    resp_item: dict[str, Any],
    detail_level: str,
) -> EvoxManifest | None:
    """Parse a single EVOX query_response item into an EvoxManifest."""
    vif_data = resp_item.get("vif") or {}
    product_data = resp_item.get("product_types") or {}
    match_level = resp_item.get("match_level", "model")
    vifid = vif_data.get("vifnum", 0) if vif_data else 0

    if not product_data:
        return None

    # Extract URLs partitioned by role
    card_urls: list[str] = []
    exterior_stills: list[str] = []
    interior_stills: list[str] = []
    spin_urls: list[str] = []
    interior_pano_url: str | None = None
    color_info: EvoxColorInfo | None = None

    for ptid_str, items in product_data.items():
        try:
            ptid = int(ptid_str)
        except (ValueError, TypeError):
            continue

        role = _PTID_ROLE_MAP.get(ptid, "unknown")
        item_list = items if isinstance(items, list) else []

        # Color filtering per PTID: different product types use different color code
        # systems (e.g. card PTIDs use "A3-D1" while stills use "AZ"), so we must
        # pick the best color independently for each PTID's item list.
        is_multi_color = len(item_list) > 1
        if is_multi_color:
            ptid_target_color = _pick_best_color_code(item_list, vehicle)
        else:
            ptid_target_color = None

        accepted_color: str | None = None

        for item in item_list:
            url = item.get("url")
            if not url:
                continue

            item_color = item.get("color_code", "")

            # For multi-color PTIDs: filter to best matching color, or first color seen
            if is_multi_color:
                if ptid_target_color:
                    if item_color != ptid_target_color:
                        continue
                else:
                    # No color match — take all items of the first color seen
                    if accepted_color is None:
                        accepted_color = item_color
                    elif item_color != accepted_color:
                        continue

            if color_info is None:
                color_info = _extract_color_info(item, vehicle)

            if role == "hero":
                card_urls.insert(0, url)  # hero first
            elif role == "gallery":
                card_urls.append(url)
            elif role == "exterior_still" and detail_level == "full":
                exterior_stills.append(url)
            elif role == "interior_still" and detail_level == "full":
                interior_stills.append(url)
            elif role == "spin" and detail_level == "full":
                spin_urls.append(url)
            elif role == "interior_pano" and detail_level == "full":
                interior_pano_url = url

    if not card_urls:
        return None

    return EvoxManifest(
        vin=vehicle.vin,
        vifid=vifid,
        color_info=color_info,
        match_level=match_level,
        hero_url=card_urls[0],
        card_gallery_urls=card_urls,
        exterior_stills=exterior_stills,
        interior_stills=interior_stills,
        spin_urls=spin_urls,
        interior_pano_url=interior_pano_url,
        vif_data=vif_data,
        available_products={k: len(v) if isinstance(v, list) else 0 for k, v in product_data.items()},
    )


def _extract_color_info(item: dict[str, Any], vehicle: Vehicle) -> EvoxColorInfo | None:
    """Extract color metadata from an EVOX image response entry."""
    color_code = item.get("color_code", "")
    color_title = item.get("color_title", "")
    color_simpletitle = item.get("color_simpletitle", "")

    if not color_code and not color_title:
        return None

    # Determine if the color matches the vehicle's exterior_color
    normalized = vehicle.features_normalized or {}
    exterior_color = (normalized.get("exterior_color") or "").strip().upper()
    is_exact = bool(exterior_color and color_simpletitle.upper() == exterior_color)

    return EvoxColorInfo(
        color_code=color_code,
        color_title=color_title,
        color_simpletitle=color_simpletitle,
        is_exact_match=is_exact,
        match_source="response_match" if is_exact else "response_default",
    )


# ---- Asset syncing ----

def sync_evox_source_assets(
    db: Session,
    *,
    vehicle: Vehicle,
    manifest: EvoxManifest,
    listing_id: str | None = None,
    source_platform: AuctionPlatform | None = None,
) -> None:
    """Persist EVOX manifest URLs as VehicleImageAsset rows (SOURCE_CACHE tier)."""
    # Load existing EVOX assets for this vehicle
    existing_assets = db.scalars(
        select(VehicleImageAsset).where(
            VehicleImageAsset.vin == vehicle.vin,
            VehicleImageAsset.tier == ImageTier.SOURCE_CACHE,
            VehicleImageAsset.source_kind == EVOX_SOURCE_KIND,
        )
    ).all()
    existing_by_url = {asset.external_url: asset for asset in existing_assets if asset.external_url}

    # Build desired asset list
    desired_assets: list[tuple[str, str, int, bool, dict[str, Any]]] = []

    color_meta: dict[str, Any] = {}
    if manifest.color_info:
        color_meta = {
            "color_code": manifest.color_info.color_code,
            "color_title": manifest.color_info.color_title,
            "color_simpletitle": manifest.color_info.color_simpletitle,
            "color_match_exact": manifest.color_info.is_exact_match,
            "color_match_source": manifest.color_info.match_source,
        }

    base_meta: dict[str, Any] = {
        "evox_vifid": manifest.vifid,
        "match_level": manifest.match_level,
        **color_meta,
    }

    order = 0
    # Card gallery (hero + angles)
    for url in manifest.card_gallery_urls:
        desired_assets.append((
            url,
            "hero" if order == 0 else "gallery",
            order,
            order == 0,
            {**base_meta, "asset_type": "card_gallery"},
        ))
        order += 1

    # Exterior stills
    for url in manifest.exterior_stills:
        desired_assets.append((
            url, "exterior_still", order, False,
            {**base_meta, "asset_type": "exterior_still"},
        ))
        order += 1

    # Interior stills
    for url in manifest.interior_stills:
        desired_assets.append((
            url, "interior_still", order, False,
            {**base_meta, "asset_type": "interior_still"},
        ))
        order += 1

    # Spin frames
    for i, url in enumerate(manifest.spin_urls):
        desired_assets.append((
            url, "spin", order, False,
            {**base_meta, "asset_type": "spin", "frame_index": i},
        ))
        order += 1

    # Interior panorama
    if manifest.interior_pano_url:
        desired_assets.append((
            manifest.interior_pano_url, "interior_pano", order, False,
            {**base_meta, "asset_type": "interior_pano"},
        ))

    # Deactivate assets no longer in desired set
    desired_urls = {url for url, *_ in desired_assets}
    for asset in existing_assets:
        asset.active = bool(asset.external_url and asset.external_url in desired_urls)

    # Upsert desired assets
    for url, role, display_order, is_primary, metadata in desired_assets:
        asset = existing_by_url.get(url)
        if asset is None:
            asset = VehicleImageAsset(
                vin=vehicle.vin,
                tier=ImageTier.SOURCE_CACHE,
                context=ImageContext.MARKETING,
                role=role,
                source_kind=EVOX_SOURCE_KIND,
                source_platform=source_platform,
                source_listing_id=listing_id,
                external_url=url,
                display_order=display_order,
                is_primary=is_primary,
                is_original=True,
                processing_status=ImageJobStatus.COMPLETED,
                metadata_json=metadata,
                active=True,
            )
            db.add(asset)
            continue

        asset.context = ImageContext.MARKETING
        asset.role = role
        asset.source_platform = source_platform
        asset.source_listing_id = listing_id
        asset.display_order = display_order
        asset.is_primary = is_primary
        asset.processing_status = ImageJobStatus.COMPLETED
        asset.metadata_json = metadata
        asset.active = True

    # Enrich vehicle with EVOX VIF metadata
    _enrich_vehicle_from_evox(db, vehicle, manifest)


def _enrich_vehicle_from_evox(db: Session, vehicle: Vehicle, manifest: EvoxManifest) -> None:
    """Update Vehicle.features_normalized with EVOX VIF metadata (fill gaps only)."""
    vif = manifest.vif_data
    if not vif:
        return

    normalized = dict(vehicle.features_normalized or {})

    def _set(key: str, value: Any) -> None:
        if value is not None and not normalized.get(key):
            normalized[key] = value

    _set("evox_vifid", manifest.vifid)
    _set("evox_match_level", manifest.match_level)
    _set("factory_doors", vif.get("doors"))
    _set("body_style_evox", vif.get("body"))
    _set("cab_config", vif.get("cab"))
    _set("drivetrain_evox", vif.get("wheels"))

    if manifest.color_info:
        _set("evox_color_code", manifest.color_info.color_code)
        _set("evox_color_title", manifest.color_info.color_title)
        _set("evox_color_simpletitle", manifest.color_info.color_simpletitle)
        _set("evox_color_match_exact", manifest.color_info.is_exact_match)

    vehicle.features_normalized = normalized

    # Fill top-level columns if null
    if not vehicle.drivetrain and vif.get("wheels"):
        vehicle.drivetrain = vif["wheels"]
    if not vehicle.body_type and vif.get("body"):
        vehicle.body_type = vif["body"]

    db.add(vehicle)


# ---- Admin-only: VIF cache sync (not in hot path) ----

def sync_vif_cache(db: Session, vif_data: list[dict[str, Any]]) -> int:
    """Sync the EVOX VIF list into the evox_vif_cache table.

    Admin-only function for coverage analytics. Not used in image resolution.
    """
    count = 0
    for row in vif_data:
        vifnum = _safe_int(row.get("VIF#") or row.get("vifnum"))
        if not vifnum:
            continue

        year = _safe_int(row.get("YR") or row.get("year"))
        make = (row.get("MAKE") or row.get("make") or "").strip()
        model = (row.get("MODEL") or row.get("model") or "").strip()
        if not year or not make or not model:
            continue

        existing = db.scalars(
            select(EvoxVifCache).where(EvoxVifCache.vifnum == vifnum)
        ).first()

        if existing:
            existing.year = year
            existing.make = make
            existing.model = model
            existing.trim = (row.get("TRIM") or row.get("trim") or "").strip()
            existing.doors = _safe_int(row.get("DRS") or row.get("doors"))
            existing.body = (row.get("BODY") or row.get("body") or "").strip() or None
            existing.cab = (row.get("CAB") or row.get("cab") or "").strip() or None
            existing.wheels = (row.get("WHLS") or row.get("wheels") or "").strip() or None
            existing.vin_photographed = (row.get("VIN") or row.get("vin_photographed") or "").strip() or None
            existing.date_delivered = (row.get("Date Delivered") or row.get("date_delivered") or "").strip() or None
            existing.has_btl = _flag(row.get("BTL") or row.get("has_btl"))
            existing.has_colors = _flag(row.get("COLORS") or row.get("has_colors"))
            existing.has_stills = _flag(row.get("STILLS") or row.get("has_stills"))
            existing.has_exterior = _flag(row.get("EXTERIOR") or row.get("has_exterior"))
            existing.has_interior = _flag(row.get("INTERIOR") or row.get("has_interior"))
            existing.has_hdspin = _flag(row.get("HDSPIN") or row.get("has_hdspin"))
            existing.has_ext_color = _flag(row.get("EXT. COLOR") or row.get("EXT.COLOR") or row.get("has_ext_color"))
            existing.active = True
        else:
            entry = EvoxVifCache(
                vifnum=vifnum,
                orgnum=_safe_int(row.get("ORG#") or row.get("orgnum")),
                sendnum=_safe_int(row.get("SEND#") or row.get("sendnum")),
                year=year,
                make=make,
                model=model,
                trim=(row.get("TRIM") or row.get("trim") or "").strip(),
                doors=_safe_int(row.get("DRS") or row.get("doors")),
                body=(row.get("BODY") or row.get("body") or "").strip() or None,
                cab=(row.get("CAB") or row.get("cab") or "").strip() or None,
                wheels=(row.get("WHLS") or row.get("wheels") or "").strip() or None,
                vin_photographed=(row.get("VIN") or row.get("vin_photographed") or "").strip() or None,
                date_delivered=(row.get("Date Delivered") or row.get("date_delivered") or "").strip() or None,
                has_btl=_flag(row.get("BTL") or row.get("has_btl")),
                has_colors=_flag(row.get("COLORS") or row.get("has_colors")),
                has_stills=_flag(row.get("STILLS") or row.get("has_stills")),
                has_exterior=_flag(row.get("EXTERIOR") or row.get("has_exterior")),
                has_interior=_flag(row.get("INTERIOR") or row.get("has_interior")),
                has_hdspin=_flag(row.get("HDSPIN") or row.get("has_hdspin")),
                has_ext_color=_flag(row.get("EXT. COLOR") or row.get("EXT.COLOR") or row.get("has_ext_color")),
                active=True,
            )
            db.add(entry)

        count += 1

    db.flush()
    return count


def parse_vif_csv(csv_content: str) -> list[dict[str, Any]]:
    """Parse VIF list CSV content into a list of dicts."""
    reader = csv.DictReader(io.StringIO(csv_content))
    return list(reader)


def _safe_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def _flag(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    try:
        return int(value) == 1
    except (ValueError, TypeError):
        return False
