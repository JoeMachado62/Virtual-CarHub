from __future__ import annotations

import csv
import io
import logging
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.constants import AuctionPlatform, ImageContext, ImageJobStatus, ImageTier
from app.integrations.evox_client import EvoxClient, EvoxColor
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
PTID_STILLS_GREY_640 = 874      # 640x480 JPEG
PTID_STILLS_GREY_1280 = 876     # 1280x960 PNG transparent

# Detail-level: stills on white background (Product ID 80)
PTID_STILLS_WHITE_640 = 882     # 640x480 JPEG
PTID_STILLS_WHITE_1280 = 883    # 1280x960 JPEG

# Exterior spinframes: 36-frame colorized (Product ID 73)
PTID_EXT_COLOR_SPIN_1280 = 831  # 1280x960, 36 frames, colorized JPEG

# Exterior spinframes: 36-frame non-colorized (Product ID 72)
PTID_EXT_SPIN_1280 = 823        # 1280x960, 36 frames, JPEG

# Interior: equirectangular panorama (Product ID 77)
PTID_INTERIOR_EQ_4000 = 862     # 4000x2000 PNG

# Card-level PTIDs (always requested)
CARD_PTIDS = [PTID_COLOR_SIDE_1280, PTID_COLOR_REAR34_1280, PTID_COLOR_FRONT34_1280]


# ---- Data classes ----

@dataclass(slots=True)
class EvoxColorMatch:
    color_code: str
    color_title: str
    color_simpletitle: str
    is_exact_match: bool
    match_source: str  # "paint_code" | "simpletitle" | "fuzzy_title" | "default"


@dataclass(slots=True)
class EvoxManifest:
    vifid: int
    color_match: EvoxColorMatch | None
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


# ---- VIF resolution ----

def resolve_vifid(db: Session, vehicle: Vehicle) -> tuple[int, EvoxVifCache] | None:
    """Look up a VIFID from the evox_vif_cache using progressive matching.

    Match priority:
    1. Exact: year + make + model + trim + body + wheels (drivetrain)
    2. Relaxed: year + make + model + trim
    3. Minimal: year + make + model (returns first match)
    """
    make_norm = (vehicle.make or "").strip()
    model_norm = (vehicle.model or "").strip()
    trim_norm = (vehicle.trim or "").strip()

    if not make_norm or not model_norm or not vehicle.year:
        return None

    base_q = (
        select(EvoxVifCache)
        .where(
            EvoxVifCache.active.is_(True),
            EvoxVifCache.year == vehicle.year,
            func.upper(EvoxVifCache.make) == make_norm.upper(),
            func.upper(EvoxVifCache.model) == model_norm.upper(),
        )
    )

    # 1. Exact match with trim + body + drivetrain
    if trim_norm:
        exact = db.scalars(
            base_q.where(func.upper(EvoxVifCache.trim) == trim_norm.upper())
        ).first()
        if exact:
            return (exact.vifnum, exact)

    # 2. Try base trim (empty trim = base model) if we have trim
    if trim_norm:
        # Some EVOX trims use different separators or abbreviations
        # Try fuzzy trim matching
        candidates = db.scalars(base_q).all()
        best_match = _fuzzy_match_trim(trim_norm, candidates)
        if best_match:
            return (best_match.vifnum, best_match)

    # 3. Minimal: year + make + model, return first
    first = db.scalars(base_q.limit(1)).first()
    if first:
        return (first.vifnum, first)

    return None


def _fuzzy_match_trim(trim: str, candidates: list[EvoxVifCache]) -> EvoxVifCache | None:
    """Find the best fuzzy trim match from candidates."""
    if not candidates:
        return None

    trim_upper = trim.upper()
    best_score = 0.0
    best_match: EvoxVifCache | None = None

    for candidate in candidates:
        candidate_trim = (candidate.trim or "").upper()
        if not candidate_trim:
            continue
        score = SequenceMatcher(None, trim_upper, candidate_trim).ratio()
        if score > best_score and score >= 0.6:
            best_score = score
            best_match = candidate

    return best_match


# ---- Color matching ----

def resolve_color_code(
    db: Session,
    vifid: int,
    vehicle: Vehicle,
) -> EvoxColorMatch | None:
    """Match the vehicle's exterior color to an EVOX color code.

    Priority:
    1. Exact paint_code / paint_id from features_normalized
    2. Match by color_simpletitle (e.g., "Black", "White")
    3. Fuzzy match on color_title (e.g., "Pearl White" -> "Crystal White")
    4. Default to first available color
    """
    normalized = vehicle.features_normalized or {}

    # Load available colors from cache
    cached_colors = db.scalars(
        select(EvoxColorCache).where(
            EvoxColorCache.vifnum == vifid,
            EvoxColorCache.active.is_(True),
        )
    ).all()

    # If no cached colors, try to fetch and cache them
    if not cached_colors:
        cached_colors = _fetch_and_cache_colors(db, vifid)

    if not cached_colors:
        return None

    # 1. Exact paint code match
    paint_code = (
        normalized.get("paint_id")
        or normalized.get("paint_code")
        or normalized.get("exterior_color_code")
    )
    if paint_code:
        paint_code_upper = paint_code.strip().upper()
        for color in cached_colors:
            if color.color_code.upper() == paint_code_upper:
                return EvoxColorMatch(
                    color_code=color.color_code,
                    color_title=color.color_title,
                    color_simpletitle=color.color_simpletitle,
                    is_exact_match=True,
                    match_source="paint_code",
                )

    # 2. Match by simpletitle
    exterior_color = (
        normalized.get("paint_description")
        or normalized.get("paint_name")
        or normalized.get("exterior_color")
        or ""
    ).strip()

    if exterior_color:
        exterior_upper = exterior_color.upper()
        for color in cached_colors:
            if color.color_simpletitle.upper() == exterior_upper:
                return EvoxColorMatch(
                    color_code=color.color_code,
                    color_title=color.color_title,
                    color_simpletitle=color.color_simpletitle,
                    is_exact_match=False,
                    match_source="simpletitle",
                )

        # 3. Fuzzy match on color_title
        best_score = 0.0
        best_color: EvoxColorCache | None = None
        for color in cached_colors:
            # Check if the simple color name appears in the exterior_color string
            if color.color_simpletitle.upper() in exterior_upper:
                return EvoxColorMatch(
                    color_code=color.color_code,
                    color_title=color.color_title,
                    color_simpletitle=color.color_simpletitle,
                    is_exact_match=False,
                    match_source="simpletitle_contains",
                )
            score = SequenceMatcher(None, exterior_upper, color.color_title.upper()).ratio()
            if score > best_score:
                best_score = score
                best_color = color

        if best_color and best_score >= 0.5:
            return EvoxColorMatch(
                color_code=best_color.color_code,
                color_title=best_color.color_title,
                color_simpletitle=best_color.color_simpletitle,
                is_exact_match=False,
                match_source="fuzzy_title",
            )

    # 4. Default to first color
    first = cached_colors[0]
    return EvoxColorMatch(
        color_code=first.color_code,
        color_title=first.color_title,
        color_simpletitle=first.color_simpletitle,
        is_exact_match=False,
        match_source="default",
    )


def _fetch_and_cache_colors(db: Session, vifid: int) -> list[EvoxColorCache]:
    """Fetch colors from EVOX API and cache them."""
    client = _get_client()
    evox_colors = client.get_vehicle_colors(vifid)
    if not evox_colors:
        return []

    cached: list[EvoxColorCache] = []
    for color in evox_colors:
        row = EvoxColorCache(
            vifnum=vifid,
            color_code=color.color_code,
            color_title=color.color_title,
            color_simpletitle=color.color_simpletitle,
            active=True,
        )
        db.add(row)
        cached.append(row)

    db.flush()
    return cached


# ---- Adaptive product type selection ----

def determine_product_types(vif_record: EvoxVifCache) -> dict[str, list[int]]:
    """Determine which EVOX product types to request based on VIF availability flags.

    Returns a dict mapping asset category to list of PTIDs.
    """
    ptids: dict[str, list[int]] = {
        "card": list(CARD_PTIDS),
        "detail_exterior_stills": [],
        "detail_interior_stills": [],
        "spin": [],
        "interior_pano": [],
    }

    # Full exterior/interior still set (Product ID 80)
    if vif_record.has_stills:
        ptids["detail_exterior_stills"] = [PTID_STILLS_GREY_1280]
        ptids["detail_interior_stills"] = [PTID_STILLS_WHITE_1280]

    # 360 exterior spin: prefer colorized when available
    if vif_record.has_ext_color:
        ptids["spin"] = [PTID_EXT_COLOR_SPIN_1280]
    elif vif_record.has_exterior:
        ptids["spin"] = [PTID_EXT_SPIN_1280]

    # Interior panorama
    if vif_record.has_interior:
        ptids["interior_pano"] = [PTID_INTERIOR_EQ_4000]

    return ptids


# ---- Manifest building ----

def build_evox_manifest(
    db: Session,
    vehicle: Vehicle,
    *,
    detail_level: str = "card",
) -> EvoxManifest | None:
    """Build an EVOX image manifest for a vehicle.

    Args:
        detail_level: "card" (hero + 3-angle gallery) or "full" (all available products).
    """
    if not settings.has_evox:
        return None

    vif_result = resolve_vifid(db, vehicle)
    if not vif_result:
        return None

    vifid, vif_record = vif_result
    color_match = resolve_color_code(db, vifid, vehicle)
    product_types = determine_product_types(vif_record)

    # Determine which PTIDs to request
    ptids_to_request: list[int] = list(product_types["card"])
    if detail_level == "full":
        ptids_to_request.extend(product_types["detail_exterior_stills"])
        ptids_to_request.extend(product_types["detail_interior_stills"])
        ptids_to_request.extend(product_types["spin"])
        ptids_to_request.extend(product_types["interior_pano"])

    # Deduplicate and limit to 10 (EVOX API max)
    ptids_to_request = list(dict.fromkeys(ptids_to_request))[:10]

    if not ptids_to_request:
        return None

    # Build the query request
    query_req: dict[str, Any] = {"vifnum": vifid}
    if color_match:
        query_req["color_code"] = color_match.color_code

    client = _get_client()
    try:
        response = client.batch_product_query(
            [query_req],
            ptids_to_request,
            webp=settings.evox_prefer_webp,
        )
    except Exception:
        logger.warning("EVOX batch_product_query failed for vifid=%s", vifid, exc_info=True)
        return None

    if response.get("source") == "stub":
        return None

    query_responses = response.get("query_responses", [])
    if not query_responses:
        return None

    resp = query_responses[0]
    vif_data = resp.get("vif", {})
    product_data = resp.get("product_types", {})
    match_level = resp.get("match_level", "model")

    # Extract URLs by product type
    card_urls = _extract_urls(product_data, CARD_PTIDS)
    ext_still_urls = _extract_urls(product_data, product_types["detail_exterior_stills"]) if detail_level == "full" else []
    int_still_urls = _extract_urls(product_data, product_types["detail_interior_stills"]) if detail_level == "full" else []
    spin_urls = _extract_urls(product_data, product_types["spin"]) if detail_level == "full" else []
    int_pano_urls = _extract_urls(product_data, product_types["interior_pano"]) if detail_level == "full" else []

    if not card_urls:
        return None

    return EvoxManifest(
        vifid=vifid,
        color_match=color_match,
        match_level=match_level,
        hero_url=card_urls[0],
        card_gallery_urls=card_urls,
        exterior_stills=ext_still_urls,
        interior_stills=int_still_urls,
        spin_urls=spin_urls,
        interior_pano_url=int_pano_urls[0] if int_pano_urls else None,
        vif_data=vif_data,
        available_products=product_types,
    )


def _extract_urls(product_data: dict, ptids: list[int]) -> list[str]:
    """Extract image URLs from EVOX product_types response for given PTIDs."""
    urls: list[str] = []
    for ptid in ptids:
        items = product_data.get(str(ptid), [])
        for item in items:
            url = item.get("url")
            if url:
                urls.append(url)
    return urls


# ---- Asset syncing ----

def sync_evox_source_assets(
    db: Session,
    *,
    vehicle: Vehicle,
    listing_id: str | None = None,
    source_platform: AuctionPlatform | None = None,
    detail_level: str = "card",
) -> EvoxManifest | None:
    """Sync EVOX images into VehicleImageAsset rows (SOURCE_CACHE tier).

    Mirrors the pattern from sync_imagin_source_assets().
    """
    manifest = build_evox_manifest(db, vehicle, detail_level=detail_level)
    if manifest is None:
        return None

    # Load existing EVOX assets for this vehicle
    existing_assets = db.scalars(
        select(VehicleImageAsset).where(
            VehicleImageAsset.vin == vehicle.vin,
            VehicleImageAsset.tier == ImageTier.SOURCE_CACHE,
            VehicleImageAsset.source_kind == EVOX_SOURCE_KIND,
        )
    ).all()
    existing_by_url = {asset.external_url: asset for asset in existing_assets if asset.external_url}

    # Build desired asset list: (url, role, display_order, is_primary, metadata)
    desired_assets: list[tuple[str, str, int, bool, dict[str, Any]]] = []

    color_meta: dict[str, Any] = {}
    if manifest.color_match:
        color_meta = {
            "color_code": manifest.color_match.color_code,
            "color_title": manifest.color_match.color_title,
            "color_simpletitle": manifest.color_match.color_simpletitle,
            "color_match_exact": manifest.color_match.is_exact_match,
            "color_match_source": manifest.color_match.match_source,
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

    return manifest


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

    if manifest.color_match:
        _set("evox_color_code", manifest.color_match.color_code)
        _set("evox_color_title", manifest.color_match.color_title)
        _set("evox_color_simpletitle", manifest.color_match.color_simpletitle)
        _set("evox_color_match_exact", manifest.color_match.is_exact_match)

    vehicle.features_normalized = normalized

    # Fill top-level columns if null
    if not vehicle.drivetrain and vif.get("wheels"):
        vehicle.drivetrain = vif["wheels"]
    if not vehicle.body_type and vif.get("body"):
        vehicle.body_type = vif["body"]

    db.add(vehicle)


# ---- VIF cache sync ----

def sync_vif_cache(db: Session, vif_data: list[dict[str, Any]]) -> int:
    """Sync the EVOX VIF list into the evox_vif_cache table.

    Args:
        vif_data: List of dicts from the parsed VIF list CSV/XLSX.
                  Each dict should have keys matching VIF list columns:
                  VIF#, ORG#, SEND#, YR, MAKE, MODEL, TRIM, DRS, BODY, CAB, WHLS,
                  VIN, Date Delivered, BTL, COLORS, STILLS, EXTERIOR, INTERIOR, HDSPIN, EXT. COLOR

    Returns:
        Number of records synced.
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
