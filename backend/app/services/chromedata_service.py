from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.constants import AuctionPlatform, ImageContext, ImageJobStatus, ImageTier
from app.integrations.chromedata_client import ChromeDataCvdClient, ChromeDataMediaClient, ChromeDataVssClient
from app.models.entities import Vehicle, VehicleImageAsset

logger = logging.getLogger(__name__)

CHROMEDATA_SOURCE_KIND = "chromedata"
CHROMEDATA_COLOR_PIPELINE_VERSION = 2

_CARD_SHOT_ORDER = ["01", "02", "03", "07", "05", "06"]
_BASIC_EXTERIOR_SHOTS = {"01", "02", "03"}  # 3-angle set used when no color match
_INTERIOR_SHOT_CODES = {
    "11", "12", "13", "17", "18", "20", "21", "28", "29", "32", "43", "44", "45", "46", "47",
}
_DETAIL_PRIORITY = {code: index for index, code in enumerate(_CARD_SHOT_ORDER + sorted(_INTERIOR_SHOT_CODES))}


@dataclass(slots=True)
class ChromeDataColorInfo:
    color_code: str
    description: str
    generic_desc: str
    install_cause: str
    rgb_hex_value: str | None
    is_exact_match: bool
    match_source: str = ""
    secondary_color_code: str = ""
    secondary_description: str = ""
    secondary_generic_desc: str = ""
    secondary_rgb_hex_value: str | None = None


@dataclass(slots=True)
class ChromeDataManifest:
    vin: str
    style_id: int | None
    match_level: str
    style_description: str | None
    body_type: str | None
    hero_url: str
    gallery_urls: list[str]
    detail_urls: list[str] = field(default_factory=list)
    color_info: ChromeDataColorInfo | None = None
    flags: dict[str, Any] = field(default_factory=dict)
    source_metadata: dict[str, Any] = field(default_factory=dict)


_cvd_client: ChromeDataCvdClient | None = None
_vss_client: ChromeDataVssClient | None = None
_media_client: ChromeDataMediaClient | None = None


def _get_cvd_client() -> ChromeDataCvdClient:
    global _cvd_client
    if _cvd_client is None:
        _cvd_client = ChromeDataCvdClient(
            base_url=settings.chromedata_cvd_base_url,
            api_key=settings.chromedata_api_key,
            api_secret=settings.chromedata_api_secret,
            profile_key=settings.chromedata_profile_key,
            live=settings.has_chromedata_vin,
        )
    return _cvd_client


def _get_vss_client() -> ChromeDataVssClient:
    global _vss_client
    if _vss_client is None:
        _vss_client = ChromeDataVssClient(
            base_url=settings.chromedata_vss_base_url,
            api_key=settings.chromedata_api_key,
            api_secret=settings.chromedata_api_secret,
            profile_key=settings.chromedata_profile_key,
            live=settings.has_chromedata_vss,
        )
    return _vss_client


def _get_media_client() -> ChromeDataMediaClient:
    global _media_client
    if _media_client is None:
        _media_client = ChromeDataMediaClient(
            base_url=settings.chromedata_media_base_url,
            username=settings.chromedata_media_username,
            password=settings.chromedata_media_password,
            live=settings.has_chromedata_media,
        )
    return _media_client


def build_chromedata_manifest(
    vehicle: Vehicle,
    *,
    detail_level: str = "card",
) -> ChromeDataManifest | None:
    if not settings.has_chromedata_media:
        return None
    if not vehicle.vin and not (vehicle.year and vehicle.make and vehicle.model):
        return None

    descriptor = _resolve_vehicle_descriptor(vehicle)
    if descriptor.get("style_id"):
        manifest = _build_style_media_manifest(vehicle, descriptor, detail_level=detail_level)
        if manifest:
            return manifest

    return _build_ymmt_media_manifest(vehicle, descriptor, detail_level=detail_level)


def batch_build_chromedata_manifests(
    vehicles: list[Vehicle],
    *,
    detail_level: str = "card",
) -> dict[str, ChromeDataManifest]:
    manifests: dict[str, ChromeDataManifest] = {}
    for vehicle in vehicles:
        manifest = build_chromedata_manifest(vehicle, detail_level=detail_level)
        if manifest:
            manifests[vehicle.vin] = manifest
    return manifests


def sync_chromedata_source_assets(
    db: Session,
    *,
    vehicle: Vehicle,
    manifest: ChromeDataManifest,
    listing_id: str | None = None,
    source_platform: AuctionPlatform | None = None,
) -> ChromeDataManifest:
    existing_assets = db.scalars(
        select(VehicleImageAsset).where(
            VehicleImageAsset.vin == vehicle.vin,
            VehicleImageAsset.tier == ImageTier.SOURCE_CACHE,
            VehicleImageAsset.source_kind == CHROMEDATA_SOURCE_KIND,
        )
    ).all()
    existing_by_url = {asset.external_url: asset for asset in existing_assets if asset.external_url}

    desired_assets: list[tuple[str, str, int, bool, dict[str, Any]]] = []
    for index, url in enumerate(manifest.gallery_urls):
        desired_assets.append(
            (
                url,
                "hero" if index == 0 else "gallery",
                index,
                index == 0,
                _asset_metadata(manifest, variant="reference", shot_code=_shot_code_from_url(url)),
            )
        )
    detail_offset = len(desired_assets)
    for index, url in enumerate(manifest.detail_urls):
        desired_assets.append(
            (
                url,
                "detail",
                detail_offset + index,
                False,
                _asset_metadata(manifest, variant="detail", shot_code=_shot_code_from_url(url)),
            )
        )

    desired_urls = {url for url, _role, _order, _primary, _metadata in desired_assets}
    for asset in existing_assets:
        asset.active = bool(asset.external_url and asset.external_url in desired_urls)

    for url, role, display_order, is_primary, metadata in desired_assets:
        asset = existing_by_url.get(url)
        if asset is None:
            asset = VehicleImageAsset(
                vin=vehicle.vin,
                tier=ImageTier.SOURCE_CACHE,
                context=ImageContext.MARKETING,
                role=role,
                source_kind=CHROMEDATA_SOURCE_KIND,
                source_platform=source_platform,
                source_listing_id=listing_id or vehicle.listing_id,
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
        asset.source_listing_id = listing_id or vehicle.listing_id
        asset.display_order = display_order
        asset.is_primary = is_primary
        asset.processing_status = ImageJobStatus.COMPLETED
        asset.metadata_json = metadata
        asset.active = True

    _enrich_vehicle_from_chromedata(vehicle, manifest)
    return manifest


def chromedata_assets_need_refresh(vehicle: Vehicle, assets: list[VehicleImageAsset]) -> bool:
    """Return true when cached ChromeData card imagery predates the color-aware
    resolver or appears to conflict with the listing exterior color."""
    card_assets = [
        asset for asset in assets
        if asset.active and asset.role in {"hero", "gallery"} and asset.source_kind == CHROMEDATA_SOURCE_KIND
    ]
    if not card_assets:
        return True

    metadata = card_assets[0].metadata_json or {}
    if metadata.get("color_pipeline_version") != CHROMEDATA_COLOR_PIPELINE_VERSION:
        return True

    listing_color = _listing_exterior_color(vehicle)
    if not listing_color or not _has_color_token(listing_color):
        return False

    if metadata.get("color_match_blocked_reason") == "listing_color_not_available":
        return False
    if metadata.get("color_match_fallback_reason") == "listing_generic_color_unavailable":
        return False

    matched_text = " ".join(
        str(value or "")
        for value in (
            metadata.get("color_description"),
            metadata.get("color_generic"),
            metadata.get("selected_color_description"),
        )
    )
    if not matched_text.strip():
        return True
    return not _color_text_matches(listing_color, matched_text)


def _resolve_vehicle_descriptor(vehicle: Vehicle) -> dict[str, Any]:
    normalized = vehicle.features_normalized or {}
    descriptor: dict[str, Any] = {
        "style_id": _coerce_int(
            normalized.get("chromedata_style_id")
            or normalized.get("style_id")
            or normalized.get("chrome_style_id")
        ),
        "match_level": "stored_style" if normalized.get("chromedata_style_id") or normalized.get("style_id") else "",
        "style_description": normalized.get("chromedata_style_description") or normalized.get("style_description"),
        "body_type": normalized.get("chromedata_body_type") or vehicle.sub_body_type or vehicle.body_type,
        "color_code": (
            normalized.get("paint_code")
            or normalized.get("exterior_color_code")
            or normalized.get("paint_id")
        ),
        "color_description": normalized.get("paint_description") or normalized.get("exterior_color"),
        "flags": {},
    }
    hmac_quota_exhausted = False
    if vehicle.vin and settings.has_chromedata_vin:
        try:
            response = _get_cvd_client().get_vin_description(vehicle.vin, locale=settings.chromedata_locale)
            cvd_descriptor = _parse_cvd_descriptor(response, vehicle)
            if cvd_descriptor:
                descriptor.update({key: value for key, value in cvd_descriptor.items() if value not in (None, "", {})})
        except httpx.HTTPStatusError as exc:
            if exc.response is not None and exc.response.status_code == 403:
                hmac_quota_exhausted = True
            logger.warning("ChromeData CVD query failed for vin=%s", vehicle.vin, exc_info=True)
        except Exception:
            logger.warning("ChromeData CVD query failed for vin=%s", vehicle.vin, exc_info=True)

    if not descriptor.get("style_id") and settings.has_chromedata_vss and not hmac_quota_exhausted:
        if vehicle.year and vehicle.make and vehicle.model:
            try:
                vss_style_id, vss_body_type, vss_description = _resolve_style_via_vss(vehicle)
                if vss_style_id:
                    descriptor["style_id"] = vss_style_id
                    descriptor["match_level"] = "vss"
                    if vss_body_type:
                        descriptor["body_type"] = vss_body_type
                    if vss_description:
                        descriptor["style_description"] = vss_description
            except Exception:
                logger.warning(
                    "ChromeData VSS style resolution failed for %s %s %s",
                    vehicle.year, vehicle.make, vehicle.model,
                    exc_info=True,
                )

    return descriptor


def _parse_cvd_descriptor(response: dict[str, Any], vehicle: Vehicle) -> dict[str, Any]:
    result = response.get("result") if isinstance(response, dict) else {}
    if not isinstance(result, dict):
        return {}

    raw_vehicles = result.get("vehicles") or result.get("vehicle") or {}
    if isinstance(raw_vehicles, list):
        vehicle_info = raw_vehicles[0] if raw_vehicles else {}
    elif isinstance(raw_vehicles, dict):
        vehicle_info = raw_vehicles
    else:
        vehicle_info = {}

    style_id = _coerce_int(
        vehicle_info.get("styleId")
        or result.get("styleId")
        or ((result.get("vehicle") or {}).get("styleId") if isinstance(result.get("vehicle"), dict) else None)
    )
    cvd_colors = _normalize_items(result.get("exteriorColors"))
    preferred_code = _normalized_color_code(vehicle)
    exterior_color_text = _listing_exterior_color(vehicle)

    selected_color = _select_listing_aware_color(
        cvd_colors,
        style_id=style_id,
        preferred_code=preferred_code,
        exterior_color_text=exterior_color_text,
    )
    selected_secondary_color = _select_secondary_color(cvd_colors, style_id=style_id)
    if selected_color and selected_secondary_color:
        selected_color.secondary_color_code = selected_secondary_color.color_code
        selected_color.secondary_description = selected_secondary_color.description
        selected_color.secondary_generic_desc = selected_secondary_color.generic_desc
        selected_color.secondary_rgb_hex_value = selected_secondary_color.rgb_hex_value

    return {
        "style_id": style_id,
        "match_level": "vin",
        "style_description": vehicle_info.get("styleDescription") or result.get("styleDescription"),
        "body_type": vehicle_info.get("bodyType") or vehicle.body_type,
        "color_code": selected_color.color_code if selected_color else "",
        "color_description": selected_color.description if selected_color else "",
        "color_info": selected_color,
        "secondary_color_code": selected_secondary_color.color_code if selected_secondary_color else "",
        "secondary_color_description": selected_secondary_color.description if selected_secondary_color else "",
        "color_match_fallback_reason": (
            "listing_generic_color_unavailable"
            if cvd_colors and exterior_color_text and _has_color_token(exterior_color_text) and not selected_color
            else ""
        ),
    }


_vss_make_cache: dict[tuple[int, str], str | None] = {}
_vss_model_cache: dict[tuple[int, str, str], str | None] = {}


def _resolve_vss_make_code(year: int, make_display: str) -> str | None:
    """Resolve a display make name (e.g. 'Ford') to the VSS makeCode via
    GET /makes.  Results are cached by (year, make_display)."""
    cache_key = (year, make_display.strip().lower())
    if cache_key in _vss_make_cache:
        return _vss_make_cache[cache_key]

    client = _get_vss_client()
    try:
        response = client.get_makes(year=year, locale=settings.chromedata_locale)
    except Exception:
        logger.debug("VSS /makes lookup failed for year=%s", year, exc_info=True)
        return None
    makes = _normalize_items(response.get("makes") or response.get("result") or response)
    target = _normalize_match_text(make_display)
    best_code: str | None = None
    for item in makes:
        code = _clean(item.get("makeCode") or item.get("code"))
        name = _clean(item.get("make") or item.get("name") or item.get("description"))
        if not code:
            continue
        if _normalize_match_text(name) == target:
            best_code = code
            break
    _vss_make_cache[cache_key] = best_code
    return best_code


def _resolve_vss_model_name(year: int, make_code: str, model_display: str) -> str | None:
    """Resolve a display model name (e.g. 'Expedition MAX') to the exact VSS
    model name via GET /models.  Cached by (year, makeCode, model_display)."""
    cache_key = (year, make_code, model_display.strip().lower())
    if cache_key in _vss_model_cache:
        return _vss_model_cache[cache_key]

    client = _get_vss_client()
    try:
        response = client.get_models(year=year, make_code=make_code, locale=settings.chromedata_locale)
    except Exception:
        logger.debug("VSS /models lookup failed for year=%s makeCode=%s", year, make_code, exc_info=True)
        return None
    models = _normalize_items(response.get("models") or response.get("result") or response)
    target = _normalize_match_text(model_display)
    best_name: str | None = None
    best_score = -1
    for item in models:
        name = _clean(item.get("model") or item.get("name") or item.get("description"))
        if not name:
            continue
        normalized_name = _normalize_match_text(name)
        if normalized_name == target:
            best_name = name
            break
        name_tokens = set(normalized_name.split())
        target_tokens = set(target.split())
        if target_tokens and target_tokens.issubset(name_tokens):
            score = len(target_tokens)
            if score > best_score:
                best_score = score
                best_name = name
    _vss_model_cache[cache_key] = best_name
    return best_name


def _resolve_style_via_vss(
    vehicle: Vehicle,
) -> tuple[int | None, str | None, str | None]:
    """Query VSS /makes → /models → /styles for the vehicle and return the
    best-matching (styleId, bodyType, styleDescription) tuple."""
    make_code = _resolve_vss_make_code(vehicle.year, vehicle.make)
    if not make_code:
        return None, None, None

    model_name = _resolve_vss_model_name(vehicle.year, make_code, vehicle.model)
    if not model_name:
        return None, None, None

    client = _get_vss_client()
    try:
        response = client.get_styles(
            year=vehicle.year,
            make_code=make_code,
            model=model_name,
            locale=settings.chromedata_locale,
        )
    except httpx.HTTPStatusError as exc:
        if exc.response is not None and exc.response.status_code == 404:
            return None, None, None
        raise
    styles = _normalize_items(response.get("styles") or response.get("result") or response)
    if not styles:
        return None, None, None

    best = _best_vss_style(styles, vehicle)
    if not best:
        return None, None, None

    style_id = _coerce_int(best.get("styleId"))
    body_type = _clean(best.get("bodyType"))
    description = _clean(
        best.get("styleDescription")
        or best.get("trimName")
        or best.get("trim")
    )
    return style_id, body_type or None, description or None


def _best_vss_style(
    styles: list[dict[str, Any]],
    vehicle: Vehicle,
) -> dict[str, Any] | None:
    """Pick the VSS style entry that best matches the vehicle's trim and body type."""
    if not styles:
        return None

    vehicle_trim = _normalize_match_text(vehicle.trim or "")
    vehicle_body = _normalize_match_text(vehicle.body_type or vehicle.sub_body_type or "")
    vehicle_trim_tokens = set(vehicle_trim.split()) if vehicle_trim else set()

    scored: list[tuple[int, int, dict[str, Any]]] = []
    for index, style in enumerate(styles):
        if not _coerce_int(style.get("styleId")):
            continue
        score = 1

        style_trim = _normalize_match_text(
            _clean(style.get("trimName") or style.get("trim") or style.get("styleDescription"))
        )
        style_body = _normalize_match_text(_clean(style.get("bodyType")))

        if vehicle_trim and style_trim:
            style_trim_tokens = set(style_trim.split())
            if vehicle_trim == style_trim:
                score += 100
            elif vehicle_trim_tokens and vehicle_trim_tokens.issubset(style_trim_tokens):
                score += 40 + len(vehicle_trim_tokens) * 4
            elif style_trim_tokens and style_trim_tokens.issubset(vehicle_trim_tokens):
                score += 30 + len(style_trim_tokens) * 3

        if vehicle_body and style_body and vehicle_body == style_body:
            score += 30

        scored.append((score, index, style))

    if not scored:
        return None

    scored.sort(key=lambda t: (-t[0], t[1]))
    return scored[0][2]


def _build_style_media_manifest(
    vehicle: Vehicle,
    descriptor: dict[str, Any],
    *,
    detail_level: str,
) -> ChromeDataManifest | None:
    style_id = descriptor.get("style_id")
    if not style_id:
        return None
    try:
        response = _get_media_client().get_style_media(style_id)
    except Exception:
        logger.warning("ChromeData style media query failed for style_id=%s", style_id, exc_info=True)
        return None
    parsed = _parse_media_response(
        response,
        detail_level=detail_level,
        selected_color_code=descriptor.get("color_code"),
        selected_secondary_color_code=descriptor.get("secondary_color_code"),
    )
    if not parsed:
        return None
    return ChromeDataManifest(
        vin=vehicle.vin,
        style_id=style_id,
        match_level=str(descriptor.get("match_level") or "style"),
        style_description=_clean(descriptor.get("style_description")),
        body_type=_clean(descriptor.get("body_type")),
        hero_url=parsed["hero_url"],
        gallery_urls=parsed["gallery_urls"],
        detail_urls=parsed["detail_urls"],
        color_info=descriptor.get("color_info"),
        flags=parsed["flags"],
        source_metadata={
            "request_type": "style",
            "resolution_source": str(descriptor.get("match_level") or "style"),
            "selected_color_code": descriptor.get("color_code"),
            "selected_color_description": descriptor.get("color_description"),
            "selected_secondary_color_code": descriptor.get("secondary_color_code"),
            "selected_secondary_color_description": descriptor.get("secondary_color_description"),
            "color_match_fallback_reason": descriptor.get("color_match_fallback_reason"),
        },
    )


def _build_ymmt_media_manifest(
    vehicle: Vehicle,
    descriptor: dict[str, Any],
    *,
    detail_level: str,
) -> ChromeDataManifest | None:
    if not vehicle.year or not vehicle.make or not vehicle.model:
        return None

    crawled_response = _crawl_media_response(vehicle, descriptor)
    if crawled_response:
        parsed = _parse_media_response(
            crawled_response["response"],
            detail_level=detail_level,
            selected_color_code=descriptor.get("color_code"),
            selected_secondary_color_code=descriptor.get("secondary_color_code"),
        )
        if parsed:
            return ChromeDataManifest(
                vin=vehicle.vin,
                style_id=descriptor.get("style_id"),
                match_level="ymmt",
                style_description=_clean(descriptor.get("style_description")),
                body_type=crawled_response["body_type"],
                hero_url=parsed["hero_url"],
                gallery_urls=parsed["gallery_urls"],
                detail_urls=parsed["detail_urls"],
                color_info=descriptor.get("color_info"),
                flags=parsed["flags"],
                source_metadata={
                    "request_type": "ymmt_crawl",
                    "selected_color_code": descriptor.get("color_code"),
                    "selected_color_description": descriptor.get("color_description"),
                    "selected_secondary_color_code": descriptor.get("secondary_color_code"),
                    "selected_secondary_color_description": descriptor.get("secondary_color_description"),
                    "color_match_fallback_reason": descriptor.get("color_match_fallback_reason"),
                    "resolved_path": crawled_response["path"],
                },
            )

    body_candidates = [
        _clean(descriptor.get("body_type")),
        _clean(vehicle.sub_body_type),
        _clean(vehicle.body_type),
        "",
    ]
    seen: set[str] = set()
    for body_type in body_candidates:
        if body_type in seen:
            continue
        seen.add(body_type)
        try:
            response = _get_media_client().get_vehicle_media(
                country=settings.chromedata_country,
                year=vehicle.year,
                division=vehicle.make,
                model=vehicle.model,
                body_type=body_type or None,
            )
        except Exception:
            logger.warning(
                "ChromeData YMM media query failed for %s %s %s body=%s",
                vehicle.year,
                vehicle.make,
                vehicle.model,
                body_type or "<model>",
                exc_info=True,
            )
            continue
        parsed = _parse_media_response(
            response,
            detail_level=detail_level,
            selected_color_code=descriptor.get("color_code"),
            selected_secondary_color_code=descriptor.get("secondary_color_code"),
        )
        if not parsed:
            continue
        return ChromeDataManifest(
            vin=vehicle.vin,
            style_id=descriptor.get("style_id"),
            match_level="ymmt",
            style_description=_clean(descriptor.get("style_description")),
            body_type=body_type or None,
            hero_url=parsed["hero_url"],
            gallery_urls=parsed["gallery_urls"],
            detail_urls=parsed["detail_urls"],
            color_info=descriptor.get("color_info"),
            flags=parsed["flags"],
            source_metadata={
                "request_type": "ymmt",
                "selected_color_code": descriptor.get("color_code"),
                "selected_color_description": descriptor.get("color_description"),
                "selected_secondary_color_code": descriptor.get("secondary_color_code"),
                "selected_secondary_color_description": descriptor.get("secondary_color_description"),
                "color_match_fallback_reason": descriptor.get("color_match_fallback_reason"),
            },
        )
    return None


def _crawl_media_response(vehicle: Vehicle, descriptor: dict[str, Any]) -> dict[str, Any] | None:
    client = _get_media_client()
    country = settings.chromedata_country
    try:
        year_response = client.get_resource(f"/{country}/{vehicle.year}")
    except Exception:
        logger.warning(
            "ChromeData year crawl failed for %s %s %s",
            vehicle.year,
            vehicle.make,
            vehicle.model,
            exc_info=True,
        )
        return None

    division_link = _best_media_link(_normalize_items(year_response.get("divisionLink")), [vehicle.make])
    if not division_link:
        return None

    try:
        division_response = client.get_resource(division_link["href"])
    except Exception:
        logger.warning("ChromeData division crawl failed for href=%s", division_link["href"], exc_info=True)
        return None

    model_candidates = [
        vehicle.model,
        descriptor.get("style_description"),
        vehicle.trim,
        descriptor.get("body_type"),
        vehicle.body_type,
    ]
    model_link = _best_media_link(_normalize_items(division_response.get("modelLink")), model_candidates)
    if not model_link:
        return None

    try:
        model_response = client.get_resource(model_link["href"])
    except Exception:
        logger.warning("ChromeData model crawl failed for href=%s", model_link["href"], exc_info=True)
        return None

    if _parse_media_response(
        model_response,
        detail_level="card",
        selected_color_code=descriptor.get("color_code"),
        selected_secondary_color_code=descriptor.get("secondary_color_code"),
    ):
        return {
            "response": model_response,
            "path": model_link["href"],
            "body_type": None,
        }

    body_links = _normalize_items(model_response.get("bodyTypeLink"))
    if not body_links:
        return None

    body_candidates = [
        descriptor.get("body_type"),
        vehicle.sub_body_type,
        vehicle.body_type,
        vehicle.trim,
        vehicle.drivetrain,
        f"{vehicle.trim or ''} {vehicle.drivetrain or ''}".strip(),
    ]
    body_link = _best_media_link(body_links, body_candidates, allow_first_fallback=True)
    if not body_link:
        return None

    try:
        body_response = client.get_resource(body_link["href"])
    except Exception:
        logger.warning("ChromeData body crawl failed for href=%s", body_link["href"], exc_info=True)
        return None

    return {
        "response": body_response,
        "path": body_link["href"],
        "body_type": body_link["label"] or None,
    }


def _parse_media_response(
    response: dict[str, Any],
    *,
    detail_level: str,
    selected_color_code: str | None,
    selected_secondary_color_code: str | None = None,
) -> dict[str, Any] | None:
    container = _media_container(response)
    if not container:
        return None

    selected_code = _clean(selected_color_code).upper()
    selected_secondary_code = _clean(selected_secondary_color_code).upper()
    colorized_images = _normalize_items(container.get("colorized"))
    if selected_code:
        matched_colorized = [
            item for item in colorized_images
            if _clean(item.get("primaryColorOptionCode") or item.get("@primaryColorOptionCode")).upper() == selected_code
        ]
        if selected_secondary_code:
            two_tone_matched = [
                item for item in matched_colorized
                if _clean(
                    item.get("secondaryColorOptionCode")
                    or item.get("@secondaryColorOptionCode")
                ).upper() == selected_secondary_code
            ]
            matched_colorized = two_tone_matched or matched_colorized
    else:
        matched_colorized = []

    # Prefer transparent background (PNG) for colorized images so they
    # composite cleanly over our dark UI.  Fall back to the full set if
    # transparent variants aren't available for a given style.
    transparent_colorized = [
        item for item in matched_colorized
        if _clean(item.get("@backgroundDescription") or item.get("backgroundDescription")).lower() == "transparent"
    ]
    preferred_colorized = transparent_colorized or matched_colorized

    # When we have a color-matched set, prefer it.  Otherwise fall through to
    # generic multi-view images — showing a random manufacturer color is worse
    # than showing a neutral view shot.
    # When we have color-matched images, show all 6 exterior angles.
    # When falling back to generic view/stock, limit to 3 basic angles
    # (01, 02, 03) to avoid showing redundant wrong-color shots.
    use_large = detail_level != "card"
    card_images = _dedupe_urls(
        _sorted_media_urls(preferred_colorized, allowed_shot_codes=set(_CARD_SHOT_ORDER), prefer_large=use_large)
        or _sorted_media_urls(_normalize_items(container.get("view")), allowed_shot_codes=_BASIC_EXTERIOR_SHOTS, prefer_large=use_large)
        or _sorted_media_urls(_normalize_items(container.get("stock")), allowed_shot_codes=_BASIC_EXTERIOR_SHOTS, prefer_large=use_large)
    )
    if not card_images:
        return None

    detail_images: list[str] = []
    if detail_level != "card":
        # Only include interior shots in the detail set.  The generic view/stock
        # exterior angles are NOT color-matched and would show a different color
        # than the colorized card images, confusing the user.
        detail_candidates = _normalize_items(container.get("view")) + _normalize_items(container.get("stock"))
        detail_images = _dedupe_urls(
            url
            for url in _sorted_media_urls(detail_candidates, allowed_shot_codes=_INTERIOR_SHOT_CODES, prefer_large=True)
            if url not in card_images
        )

    flags = container.get("flags") if isinstance(container.get("flags"), dict) else {}
    if not flags and preferred_colorized:
        item_flags = preferred_colorized[0].get("flags")
        flags = item_flags if isinstance(item_flags, dict) else {}
    return {
        "hero_url": card_images[0],
        "gallery_urls": card_images,
        "detail_urls": detail_images,
        "flags": {
            "carry_over": _truthy(flags.get("carryOver")),
            "exact_match": _truthy(flags.get("exactMatch")),
            "oem_temp": _truthy(flags.get("oemTemp")),
        },
    }


def _media_container(response: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(response, dict):
        return {}
    for key in ("styleMedia", "bodyTypeMedia", "modelMedia"):
        value = response.get(key)
        if isinstance(value, dict):
            return value
    return response


def _normalize_items(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if isinstance(value, dict):
        item_keys = {
            "colorCode", "genericDesc", "description", "styleId", "styleDescription",
            "href", "@href", "xl:href", "@xl:href", "url", "primaryColorOptionCode",
            "@primaryColorOptionCode", "shotCode", "@shotCode",
        }
        if any(key in value for key in item_keys):
            return [value]
        if any(isinstance(inner, list) for inner in value.values()):
            items: list[dict[str, Any]] = []
            for inner in value.values():
                items.extend(_normalize_items(inner))
            return items
        return [value]
    return []


def _sorted_media_urls(
    items: list[dict[str, Any]],
    allowed_shot_codes: set[str] | None = None,
    *,
    prefer_large: bool = False,
) -> list[str]:
    records: dict[str, tuple[int, int, int, str]] = {}
    for item in items:
        url = _extract_url(item)
        if not url:
            continue
        shot_code = _shot_code(item)
        if allowed_shot_codes is not None and shot_code and shot_code not in allowed_shot_codes:
            continue
        order = _DETAIL_PRIORITY.get(shot_code, 999)
        bg = _clean(item.get("@backgroundDescription") or item.get("backgroundDescription")).lower()
        bg_rank = 0 if bg == "transparent" else 1
        width_rank = _width_rank(item, prefer_large=prefer_large)
        key = shot_code or url
        existing = records.get(key)
        candidate = (order, bg_rank, width_rank, url)
        if existing is None or candidate[:3] < existing[:3]:
            records[key] = candidate
    return [url for _order, _bg, _wr, url in sorted(records.values())]


def _primary_color_group(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not items:
        return []
    primary_code = _clean(items[0].get("primaryColorOptionCode")).upper()
    if not primary_code:
        return items
    return [
        item for item in items
        if _clean(item.get("primaryColorOptionCode") or item.get("@primaryColorOptionCode")).upper() == primary_code
    ]


_WIDTH_RANK_CARD = {640: 0, 1280: 1, 320: 2, 2100: 3}
_WIDTH_RANK_FULL = {1280: 0, 2100: 1, 640: 2, 320: 3}


def _width_rank(item: dict[str, Any], *, prefer_large: bool = False) -> int:
    width = _coerce_int(item.get("@width") or item.get("width"))
    if width is None:
        return 99
    preference = _WIDTH_RANK_FULL if prefer_large else _WIDTH_RANK_CARD
    return preference.get(width, 10 + abs(width - 1280 if prefer_large else width - 640))


def _extract_url(item: dict[str, Any]) -> str:
    for key in ("href", "xl:href", "@xl:href", "url", "@href", "$", "#text"):
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    link = item.get("link")
    if isinstance(link, dict):
        for key in ("href", "xl:href", "url"):
            value = link.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return ""


def _best_media_link(
    items: list[dict[str, Any]],
    candidates: list[object | None],
    *,
    allow_first_fallback: bool = False,
) -> dict[str, str] | None:
    links: list[dict[str, str]] = []
    for item in items:
        href = _clean(item.get("@href") or item.get("href"))
        label = _clean(item.get("$") or item.get("label") or item.get("name"))
        if href:
            links.append({"href": href, "label": label})
    if not links:
        return None

    best: dict[str, str] | None = None
    best_score = -1
    for link in links:
        score = _media_link_score(link["label"], candidates)
        if score > best_score:
            best = link
            best_score = score

    if best and best_score > 0:
        return best
    if allow_first_fallback:
        return links[0]
    return None


def _media_link_score(label: str, candidates: list[object | None]) -> int:
    normalized_label = _normalize_match_text(label)
    if not normalized_label:
        return 0

    label_tokens = set(normalized_label.split())
    score = 0
    for candidate in candidates:
        raw = _clean(candidate)
        if not raw:
            continue
        for variant in _candidate_variants(raw):
            normalized_candidate = _normalize_match_text(variant)
            if not normalized_candidate:
                continue
            candidate_tokens = set(normalized_candidate.split())
            if normalized_label == normalized_candidate:
                score = max(score, 100)
            elif normalized_candidate in normalized_label:
                score = max(score, 60 + len(candidate_tokens) * 5)
            elif candidate_tokens and candidate_tokens.issubset(label_tokens):
                score = max(score, 40 + len(candidate_tokens) * 4)
            elif label_tokens and label_tokens.issubset(candidate_tokens):
                score = max(score, 20 + len(label_tokens) * 2)
    return score


def _candidate_variants(value: str) -> list[str]:
    variants = {value}
    normalized = _normalize_match_text(value)
    if "4wd" in normalized:
        variants.add(value.replace("4WD", "4x4").replace("4wd", "4x4"))
    if "awd" in normalized:
        variants.add(value.replace("AWD", "All Wheel Drive").replace("awd", "all wheel drive"))
    if "fwd" in normalized:
        variants.add(value.replace("FWD", "Front Wheel Drive").replace("fwd", "front wheel drive"))
    if "rwd" in normalized:
        variants.add(value.replace("RWD", "Rear Wheel Drive").replace("rwd", "rear wheel drive"))
    return list(variants)


def _normalize_match_text(value: str) -> str:
    normalized = _clean(value).lower()
    normalized = normalized.replace("&", " and ").replace("/", " ")
    normalized = normalized.replace("4x4", "4wd")
    normalized = re.sub(r"[^a-z0-9]+", " ", normalized)
    return " ".join(part for part in normalized.split() if part)


def _shot_code(item: dict[str, Any]) -> str:
    value = item.get("shotCode") or item.get("@shotCode") or item.get("shot_code")
    if value is None:
        return ""
    code = str(value).strip()
    return code.zfill(2) if code.isdigit() and len(code) < 2 else code


def _select_listing_aware_color(
    colors: list[dict[str, Any]],
    *,
    style_id: int | None,
    preferred_code: str | None,
    exterior_color_text: str,
) -> ChromeDataColorInfo | None:
    if not colors:
        return None

    candidates = _style_body_color_candidates(colors, style_id=style_id)
    installed = [item for item in candidates if _is_exact_color(item)]

    if exterior_color_text:
        text_match = _match_color_by_text(installed, exterior_color_text) if installed else None
        if text_match:
            return _select_color_info(candidates, style_id=style_id, preferred_code=text_match, match_source="vin_listing_text")

        text_match = _match_color_by_text(candidates, exterior_color_text)
        if text_match:
            return _select_color_info(candidates, style_id=style_id, preferred_code=text_match, match_source="listing_text")

        if _has_color_token(exterior_color_text):
            return None

    selected = _select_color_info(candidates, style_id=style_id, preferred_code=preferred_code, match_source="stored_code")
    if selected and selected.color_code:
        return selected

    if installed:
        return _to_color_info(installed[0], exact_override=True, match_source="vin_installed")

    return _select_color_info(candidates, style_id=style_id, preferred_code=None, match_source="cvd_primary")


def _select_secondary_color(colors: list[dict[str, Any]], *, style_id: int | None) -> ChromeDataColorInfo | None:
    secondary_candidates = [
        item for item in colors
        if str(item.get("type") or "") in {"2", "3"}
    ]
    if style_id:
        style_text = str(style_id)
        style_matches = [
            item for item in secondary_candidates
            if style_text in {str(value) for value in _style_ids_for_color(item)}
        ]
        if style_matches:
            secondary_candidates = style_matches

    installed_secondary = [item for item in secondary_candidates if _is_exact_color(item)]
    if installed_secondary:
        return _to_color_info(installed_secondary[0], exact_override=True, match_source="vin_secondary")

    primary_secondary = next((item for item in secondary_candidates if _truthy(item.get("primary"))), None)
    if primary_secondary:
        return _to_color_info(primary_secondary, exact_override=False, match_source="cvd_secondary_primary")

    return None


def _style_body_color_candidates(colors: list[dict[str, Any]], *, style_id: int | None) -> list[dict[str, Any]]:
    body_colors = [item for item in colors if str(item.get("type") or "") in {"", "1"}]
    candidates = body_colors or colors
    if not style_id:
        return candidates
    style_text = str(style_id)
    style_matches = [
        item for item in candidates
        if style_text in {str(value) for value in _style_ids_for_color(item)}
    ]
    return style_matches or candidates


def _style_ids_for_color(item: dict[str, Any]) -> list[Any]:
    styles = item.get("styles") or item.get("styleIds") or item.get("styleID") or item.get("styleId")
    if isinstance(styles, list):
        return styles
    if styles in (None, ""):
        return []
    return [styles]


def _select_color_info(
    colors: list[dict[str, Any]],
    *,
    style_id: int | None,
    preferred_code: str | None,
    match_source: str = "",
) -> ChromeDataColorInfo | None:
    if not colors:
        return None
    preferred = _clean(preferred_code).upper()
    if preferred:
        for item in colors:
            if _clean(item.get("colorCode")).upper() == preferred:
                return _to_color_info(item, exact_override=True, match_source=match_source)

    candidates = _style_body_color_candidates(colors, style_id=style_id)

    primary = next((item for item in candidates if _truthy(item.get("primary"))), None)
    if primary:
        return _to_color_info(primary, exact_override=_is_exact_color(primary), match_source=match_source)

    return _to_color_info(
        candidates[0],
        exact_override=_is_exact_color(candidates[0]) and len(candidates) == 1,
        match_source=match_source,
    )


def _match_color_by_text(colors: list[dict[str, Any]], exterior_text: str) -> str | None:
    """Match a free-text exterior color (e.g. 'Black') against CVD color
    descriptions and genericDesc to find the best colorCode."""
    target = _normalize_match_text(exterior_text)
    if not target:
        return None
    target_tokens = set(target.split())
    target_color_tokens = _canonical_color_tokens(target_tokens)

    best_code: str | None = None
    best_score = 0
    for item in colors:
        code = _clean(item.get("colorCode"))
        if not code:
            continue
        for field in ("genericDesc", "description"):
            desc = _normalize_match_text(_clean(item.get(field)))
            if not desc:
                continue
            desc_tokens = set(desc.split())
            desc_color_tokens = _canonical_color_tokens(desc_tokens)
            if target == desc:
                return code  # exact match — return immediately
            if target_color_tokens and desc_color_tokens and target_color_tokens & desc_color_tokens:
                score = 80 + len(target_color_tokens & desc_color_tokens)
                if score > best_score:
                    best_score = score
                    best_code = code
            if target_tokens and target_tokens.issubset(desc_tokens):
                score = 60 + len(target_tokens)
                if score > best_score:
                    best_score = score
                    best_code = code
            elif desc_tokens and desc_tokens.issubset(target_tokens):
                score = 40 + len(desc_tokens)
                if score > best_score:
                    best_score = score
                    best_code = code
    return best_code


def _to_color_info(item: dict[str, Any], *, exact_override: bool, match_source: str) -> ChromeDataColorInfo:
    return ChromeDataColorInfo(
        color_code=_clean(item.get("colorCode")),
        description=_clean(item.get("description")),
        generic_desc=_clean(item.get("genericDesc")),
        install_cause=_clean(item.get("installCause")),
        rgb_hex_value=_clean(item.get("rgbHexValue")) or None,
        is_exact_match=exact_override,
        match_source=match_source,
    )


def _is_exact_color(item: dict[str, Any]) -> bool:
    install_cause = _clean(item.get("installCause")).upper()
    return install_cause in {"B", "E", "V", "I"}


def _normalized_color_code(vehicle: Vehicle) -> str:
    normalized = vehicle.features_normalized or {}
    return _clean(
        normalized.get("paint_code")
        or normalized.get("exterior_color_code")
        or normalized.get("paint_id")
    )


_COLOR_WORDS = {
    "black", "blue", "brown", "gold", "gray", "grey", "green", "orange", "purple",
    "red", "silver", "tan", "white", "yellow", "beige", "bronze", "copper",
    "charcoal", "maroon", "pearl", "metallic",
}

_COLOR_ALIASES = {
    "grey": "gray",
    "charcoal": "gray",
    "pearl": "white",
    "beige": "tan",
    "bronze": "brown",
    "copper": "brown",
    "maroon": "red",
}


def _canonical_color_tokens(tokens: set[str]) -> set[str]:
    return {
        _COLOR_ALIASES.get(token, token)
        for token in tokens
        if token in _COLOR_WORDS
    }


def _listing_exterior_color(vehicle: Vehicle) -> str:
    normalized_features = vehicle.features_normalized or {}
    return _clean(
        normalized_features.get("exterior_color")
        or normalized_features.get("exterior_color_description")
        or normalized_features.get("paint_description")
        or (vehicle.exterior_color if hasattr(vehicle, "exterior_color") else "")
    )


def _has_color_token(value: str) -> bool:
    tokens = set(_normalize_match_text(value).split())
    return bool(tokens & _COLOR_WORDS)


def _color_text_matches(needle: str, haystack: str) -> bool:
    target = _normalize_match_text(needle)
    candidate = _normalize_match_text(haystack)
    if not target or not candidate:
        return False
    target_tokens = set(target.split())
    candidate_tokens = set(candidate.split())
    color_tokens = _canonical_color_tokens(target_tokens)
    candidate_color_tokens = _canonical_color_tokens(candidate_tokens)
    if color_tokens:
        return bool(color_tokens & candidate_color_tokens)
    return target == candidate or target in candidate or candidate in target


def _asset_metadata(manifest: ChromeDataManifest, *, variant: str, shot_code: str | None) -> dict[str, Any]:
    return {
        "provider": CHROMEDATA_SOURCE_KIND,
        "color_pipeline_version": CHROMEDATA_COLOR_PIPELINE_VERSION,
        "variant": variant,
        "style_id": manifest.style_id,
        "style_description": manifest.style_description,
        "body_type": manifest.body_type,
        "match_level": manifest.match_level,
        "shot_code": shot_code,
        "color_code": manifest.color_info.color_code if manifest.color_info else "",
        "color_description": manifest.color_info.description if manifest.color_info else "",
        "color_generic": manifest.color_info.generic_desc if manifest.color_info else "",
        "secondary_color_code": manifest.color_info.secondary_color_code if manifest.color_info else "",
        "secondary_color_description": manifest.color_info.secondary_description if manifest.color_info else "",
        "secondary_color_generic": manifest.color_info.secondary_generic_desc if manifest.color_info else "",
        "color_match_exact": bool(manifest.color_info and manifest.color_info.is_exact_match),
        "color_match_source": manifest.color_info.match_source if manifest.color_info else "",
        "flags": manifest.flags,
        **manifest.source_metadata,
    }


def _enrich_vehicle_from_chromedata(vehicle: Vehicle, manifest: ChromeDataManifest) -> None:
    normalized = dict(vehicle.features_normalized or {})

    def _set(key: str, value: Any) -> None:
        if value not in (None, "", [], {}) and not normalized.get(key):
            normalized[key] = value

    _set("chromedata_style_id", manifest.style_id)
    _set("chromedata_style_description", manifest.style_description)
    _set("chromedata_match_level", manifest.match_level)
    _set("chromedata_body_type", manifest.body_type)
    if manifest.color_info:
        _set("exterior_color_code", manifest.color_info.color_code)
        _set("paint_code", manifest.color_info.color_code)
        _set("exterior_color", manifest.color_info.description or manifest.color_info.generic_desc)
        _set("paint_description", manifest.color_info.description)
        _set("chromedata_color_exact", manifest.color_info.is_exact_match)
    vehicle.features_normalized = normalized


def _shot_code_from_url(url: str) -> str | None:
    if "shotCode=" not in url:
        return None
    value = url.split("shotCode=", 1)[1].split("&", 1)[0].strip()
    if not value:
        return None
    return value.zfill(2) if value.isdigit() and len(value) < 2 else value


def _dedupe_urls(urls: Any) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for raw in urls:
        url = _clean(raw)
        if not url or url in seen:
            continue
        seen.add(url)
        ordered.append(url)
    return ordered


def _coerce_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y"}


def _clean(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()
