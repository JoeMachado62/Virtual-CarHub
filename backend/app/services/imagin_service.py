from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlencode

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.constants import AuctionPlatform, ImageContext, ImageJobStatus, ImageTier, InventorySourceType
from app.models.entities import Vehicle, VehicleImageAsset


IMAGIN_SOURCE_KIND = "imagin"


@dataclass(slots=True)
class ImaginManifest:
    spec: dict[str, str]
    hero_url: str
    gallery_urls: list[str]
    spin_urls: list[str]
    metadata: dict[str, object]


def build_imagin_manifest(vehicle: Vehicle) -> ImaginManifest | None:
    if not settings.has_imagin or not _is_auction_vehicle(vehicle):
        return None

    spec = _build_spec(vehicle)
    if not spec.get("make") or not spec.get("modelFamily"):
        return None

    gallery_angles = _gallery_angles()
    if not gallery_angles:
        return None

    hero_angle = gallery_angles[0]
    hero_url = _build_url(spec, angle=hero_angle, zoom_type="fullscreen")
    gallery_urls = [_build_url(spec, angle=angle, zoom_type="fullscreen") for angle in gallery_angles]

    spin_urls: list[str] = []
    if settings.imagin_spin_enabled:
        for offset in range(max(0, settings.imagin_spin_frame_count)):
            spin_urls.append(
                _build_url(
                    spec,
                    angle=str(settings.imagin_spin_start_angle + offset),
                    zoom_type="adaptive",
                )
            )

    metadata = {
        "spec": spec,
        "hero_angle": hero_angle,
        "gallery_angles": gallery_angles,
        "spin_enabled": settings.imagin_spin_enabled,
        "spin_frame_count": len(spin_urls),
        "has_exact_exterior_color": bool(spec.get("paintId")),
        "has_exact_interior_color": bool(spec.get("interiorId")),
    }
    return ImaginManifest(
        spec=spec,
        hero_url=hero_url,
        gallery_urls=gallery_urls,
        spin_urls=spin_urls,
        metadata=metadata,
    )


def sync_imagin_source_assets(
    db: Session,
    *,
    vehicle: Vehicle,
    listing_id: str | None,
    source_platform: AuctionPlatform | None,
) -> ImaginManifest | None:
    manifest = build_imagin_manifest(vehicle)
    if manifest is None:
        return None

    existing_assets = db.scalars(
        select(VehicleImageAsset).where(
            VehicleImageAsset.vin == vehicle.vin,
            VehicleImageAsset.tier == ImageTier.SOURCE_CACHE,
            VehicleImageAsset.source_kind == IMAGIN_SOURCE_KIND,
        )
    ).all()
    existing_by_url = {asset.external_url: asset for asset in existing_assets if asset.external_url}

    desired_assets: list[tuple[str, str, int, bool, dict[str, object]]] = []
    for index, url in enumerate(manifest.gallery_urls):
        desired_assets.append(
            (
                url,
                "hero" if index == 0 else "gallery",
                index,
                index == 0,
                {
                    "variant": "static",
                    "angle": manifest.metadata.get("gallery_angles", [])[index] if index < len(manifest.gallery_urls) else "",
                    **manifest.metadata,
                },
            )
        )
    spin_offset = len(manifest.gallery_urls)
    for index, url in enumerate(manifest.spin_urls):
        desired_assets.append(
            (
                url,
                "spin",
                spin_offset + index,
                False,
                {
                    "variant": "spin",
                    "angle": settings.imagin_spin_start_angle + index,
                    **manifest.metadata,
                },
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
                source_kind=IMAGIN_SOURCE_KIND,
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

    return manifest


def _build_spec(vehicle: Vehicle) -> dict[str, str]:
    normalized = vehicle.features_normalized or {}
    spec: dict[str, str] = {
        "customer": settings.imagin_customer_id.strip(),
        "make": _clean(vehicle.make),
        "modelFamily": _clean(vehicle.model),
    }

    model_year = str(vehicle.year).strip() if vehicle.year else ""
    if model_year:
        spec["modelYear"] = model_year

    trim = _clean(vehicle.trim)
    if trim:
        spec["trim"] = trim

    model_variant = _clean(vehicle.sub_body_type) or _clean(vehicle.body_type)
    if model_variant:
        spec["modelVariant"] = model_variant

    power_train = _derive_powertrain(vehicle)
    if power_train:
        spec["powerTrain"] = power_train

    transmission = _clean(normalized.get("transmission"))
    if transmission:
        spec["transmission"] = transmission

    steering = _clean(normalized.get("steering")) or _clean(settings.imagin_default_steering)
    if steering:
        spec["steering"] = steering

    country_code = _clean(normalized.get("country_code")) or _clean(settings.imagin_country_code)
    if country_code:
        spec["countryCode"] = country_code

    exterior_color = _clean(
        normalized.get("paint_description")
        or normalized.get("paint_name")
        or normalized.get("exterior_color")
    )
    exterior_color_code = _clean(
        normalized.get("paint_id")
        or normalized.get("paint_code")
        or normalized.get("exterior_color_code")
    )
    if exterior_color_code:
        spec["paintId"] = exterior_color_code
    if exterior_color:
        spec["paintDescription"] = exterior_color

    interior_color = _clean(
        normalized.get("interior_description")
        or normalized.get("interior_name")
        or normalized.get("interior_color")
    )
    interior_color_code = _clean(
        normalized.get("interior_id")
        or normalized.get("interior_code")
        or normalized.get("interior_color_code")
    )
    if interior_color_code:
        spec["interiorId"] = interior_color_code
    if interior_color:
        spec["interiorDescription"] = interior_color

    return {key: value for key, value in spec.items() if value}


def _build_url(spec: dict[str, str], *, angle: str, zoom_type: str) -> str:
    params = dict(spec)
    params["angle"] = angle
    params["zoomType"] = zoom_type
    return f"{settings.imagin_cdn_base_url}?{urlencode(params)}"


def _gallery_angles() -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in settings.imagin_gallery_angle_list:
        if value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered


def _clean(value: object) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return text


def _derive_powertrain(vehicle: Vehicle) -> str:
    normalized = vehicle.features_normalized or {}
    candidates = [
        _clean(normalized.get("powertrain")),
        _clean(normalized.get("fuel_type")),
        _clean(vehicle.engine_type),
    ]
    combined = " ".join(value.lower() for value in candidates if value)
    if not combined:
        return ""
    if "hydrogen" in combined or "fuel cell" in combined:
        return "hydrogen"
    if "plug" in combined and "hybrid" in combined:
        return "plug-in hybrid"
    if "hybrid" in combined:
        return "hybrid"
    if "electric" in combined or "bev" in combined or "ev" == combined:
        return "electric"
    if "diesel" in combined:
        return "diesel"
    if "petrol" in combined or "gas" in combined or "gasoline" in combined:
        return "petrol"
    return candidates[0]


def _is_auction_vehicle(vehicle: Vehicle) -> bool:
    source_type = _clean(vehicle.source_type).lower()
    return source_type in {InventorySourceType.OVE.value, InventorySourceType.AUCTION.value}
