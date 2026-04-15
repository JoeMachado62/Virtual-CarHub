from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.constants import (
    AuctionPlatform,
    DealState,
    ImageContext,
    ImageDisplayMode,
    ImageJobStatus,
    ImageTier,
    InspectionStatus,
)
from app.models.entities import (
    OveVehicleDetail,
    Vehicle,
    VehicleImageAsset,
    VehicleImageJob,
    VehicleInspectionImage,
    VehicleInspectionReport,
)
from app.core.config import settings
from app.services.evox_service import EVOX_SOURCE_KIND
from app.services.imagin_service import IMAGIN_SOURCE_KIND, build_imagin_manifest
from app.services.object_storage import resolve_storage_url


INSPECTION_DRIVEN_STATES = {
    DealState.ACQUISITION_PENDING,
    DealState.ACQUIRED,
    DealState.IN_TRANSIT,
    DealState.DELIVERED,
    DealState.RETURN_PENDING,
    DealState.CLOSED_WON,
    DealState.CLOSED_LOST,
}

READY_INSPECTION_STATUSES = {
    InspectionStatus.INGESTED,
    InspectionStatus.NORMALIZED,
    InspectionStatus.VERIFIED,
}


@dataclass(slots=True)
class VehicleCardMedia:
    thumbnail: str | None
    display_mode: ImageDisplayMode
    inspection_status: InspectionStatus
    has_inspection_report: bool
    dealer_photos_gated: bool = False
    gated_photo_count: int = 0
    evox_pending: bool = False


def sync_marketcheck_source_assets(
    db: Session,
    *,
    vin: str,
    listing_id: str | None,
    image_urls: list[str],
) -> None:
    sync_source_assets(
        db,
        vin=vin,
        listing_id=listing_id,
        image_urls=image_urls,
        source_kind="marketcheck",
    )


def sync_source_assets(
    db: Session,
    *,
    vin: str,
    listing_id: str | None,
    image_urls: list[str],
    source_kind: str,
    source_platform: AuctionPlatform | None = None,
    context: ImageContext = ImageContext.MARKETING,
    role: str = "reference",
) -> None:
    if not image_urls:
        return

    # Filter out GIF/SVG files — these are typically UI elements (logos, icons)
    # scraped from auction sites, not actual vehicle photos
    BLOCKED_EXTENSIONS = (".gif", ".svg")
    BLOCKED_FILENAMES = {"ready_logistics.png"}
    normalized = []
    for url in image_urls:
        clean = str(url).strip()
        if not clean:
            continue
        # Check the path portion (before query string) for blocked extensions
        path_part = clean.split("?")[0].lower()
        if any(path_part.endswith(ext) for ext in BLOCKED_EXTENSIONS):
            continue
        # Block specific known non-vehicle images by filename
        filename = path_part.rsplit("/", 1)[-1]
        if filename in BLOCKED_FILENAMES:
            continue
        normalized.append(clean)
    if not normalized:
        return

    existing_assets = db.scalars(
        select(VehicleImageAsset).where(
            VehicleImageAsset.vin == vin,
            VehicleImageAsset.tier == ImageTier.SOURCE_CACHE,
        )
    ).all()
    existing_by_url = {asset.external_url: asset for asset in existing_assets if asset.external_url}

    for index, url in enumerate(normalized):
        asset = existing_by_url.get(url)
        if not asset:
            asset = VehicleImageAsset(
                vin=vin,
                tier=ImageTier.SOURCE_CACHE,
                context=context,
                role=role,
                source_kind=source_kind,
                source_platform=source_platform,
                source_listing_id=listing_id,
                external_url=url,
                display_order=index,
                is_primary=index == 0,
                is_original=True,
                processing_status=ImageJobStatus.COMPLETED,
                metadata_json={},
                active=True,
            )
            db.add(asset)
            continue

        asset.source_listing_id = listing_id
        asset.source_kind = source_kind
        asset.source_platform = source_platform
        asset.context = context
        asset.role = role
        asset.display_order = index
        asset.is_primary = index == 0
        asset.active = True
        asset.processing_status = ImageJobStatus.COMPLETED


def ensure_tier2_hero_job(
    db: Session,
    *,
    vin: str,
    trigger_event: str,
    primary_image_url: str | None,
) -> VehicleImageJob | None:
    if not primary_image_url:
        return None

    fingerprint = _fingerprint(vin=vin, tier=ImageTier.TIER2_HERO, payload=[primary_image_url])
    existing = db.scalar(
        select(VehicleImageJob).where(
            VehicleImageJob.vin == vin,
            VehicleImageJob.tier == ImageTier.TIER2_HERO,
            VehicleImageJob.source_fingerprint == fingerprint,
            VehicleImageJob.status.in_([ImageJobStatus.PENDING, ImageJobStatus.PROCESSING, ImageJobStatus.COMPLETED]),
        )
    )
    if existing:
        return existing

    job = VehicleImageJob(
        vin=vin,
        tier=ImageTier.TIER2_HERO,
        trigger_event=trigger_event,
        status=ImageJobStatus.PENDING,
        source_fingerprint=fingerprint,
        manifest_json={
            "vin": vin,
            "tier": ImageTier.TIER2_HERO.value,
            "source_primary_image": primary_image_url,
            "queued_at": datetime.now(UTC).isoformat(),
        },
    )
    db.add(job)
    # SessionLocal disables autoflush, so persist now to make dedupe idempotent
    # for repeated calls in the same transaction.
    db.flush()
    return job


def ensure_tier3_processing_job(
    db: Session,
    *,
    vin: str,
    trigger_event: str,
    source_image_urls: list[str],
) -> VehicleImageJob | None:
    cleaned = [str(url).strip() for url in source_image_urls if str(url).strip()]
    if not cleaned:
        return None

    fingerprint = _fingerprint(vin=vin, tier=ImageTier.TIER3_PROCESSED, payload=cleaned)
    existing = db.scalar(
        select(VehicleImageJob).where(
            VehicleImageJob.vin == vin,
            VehicleImageJob.tier == ImageTier.TIER3_PROCESSED,
            VehicleImageJob.source_fingerprint == fingerprint,
            VehicleImageJob.status.in_([ImageJobStatus.PENDING, ImageJobStatus.PROCESSING, ImageJobStatus.COMPLETED]),
        )
    )
    if existing:
        return existing

    job = VehicleImageJob(
        vin=vin,
        tier=ImageTier.TIER3_PROCESSED,
        trigger_event=trigger_event,
        status=ImageJobStatus.PENDING,
        source_fingerprint=fingerprint,
        manifest_json={
            "vin": vin,
            "tier": ImageTier.TIER3_PROCESSED.value,
            "image_count": len(cleaned),
            "queued_at": datetime.now(UTC).isoformat(),
        },
    )
    db.add(job)
    # SessionLocal disables autoflush, so persist now to make dedupe idempotent
    # for repeated calls in the same transaction.
    db.flush()
    return job


def resolve_vehicle_card_media(
    db: Session,
    *,
    vehicle: Vehicle,
    deal_stage: DealState | None = None,
    deal_id: str | None = None,
    is_garage_view: bool = False,
    allow_protected_photos: bool = False,
) -> VehicleCardMedia:
    context = resolve_vehicle_display_context(
        db,
        vehicle=vehicle,
        deal_stage=deal_stage,
        deal_id=deal_id,
        is_garage_view=is_garage_view,
        allow_protected_photos=allow_protected_photos,
    )
    return VehicleCardMedia(
        thumbnail=context.get("hero_image"),
        display_mode=ImageDisplayMode(context["mode"]),
        inspection_status=InspectionStatus(context["inspection_status"]),
        has_inspection_report=bool(context.get("has_inspection_report")),
        dealer_photos_gated=bool(context.get("dealer_photos_gated")),
        gated_photo_count=int(context.get("gated_photo_count", 0)),
        evox_pending=bool(context.get("evox_pending")),
    )


_BLOCKED_IMAGE_EXTENSIONS = (".gif", ".svg")
_BLOCKED_IMAGE_FILENAMES = {"ready_logistics.png"}


def _filter_non_photo_urls(urls: list[str]) -> list[str]:
    """Remove GIF/SVG URLs and known non-vehicle images."""
    out = []
    for url in urls:
        path_part = url.split("?")[0].lower()
        if any(path_part.endswith(ext) for ext in _BLOCKED_IMAGE_EXTENSIONS):
            continue
        filename = path_part.rsplit("/", 1)[-1]
        if filename in _BLOCKED_IMAGE_FILENAMES:
            continue
        out.append(url)
    return out


def _partition_ove_detail_images(images_json: list[Any] | None) -> tuple[list[str], list[str], list[str]]:
    gallery: list[str] = []
    inspection: list[str] = []
    disclosure: list[str] = []
    seen: set[str] = set()

    for entry in images_json or []:
        url: str | None = None
        role = "gallery"
        if isinstance(entry, str):
            url = entry.strip()
        elif isinstance(entry, dict):
            raw_url = entry.get("url")
            if isinstance(raw_url, str):
                url = raw_url.strip()
            raw_role = entry.get("role")
            if isinstance(raw_role, str) and raw_role.strip():
                role = raw_role.strip().lower()

        if not url:
            continue
        filtered = _filter_non_photo_urls([url])
        if not filtered:
            continue
        cleaned_url = filtered[0]
        if cleaned_url in seen:
            continue
        seen.add(cleaned_url)

        if role == "disclosure":
            disclosure.append(cleaned_url)
        elif role == "inspection":
            inspection.append(cleaned_url)
        else:
            gallery.append(cleaned_url)

    return gallery, inspection, disclosure


def resolve_vehicle_display_context(
    db: Session,
    *,
    vehicle: Vehicle,
    deal_stage: DealState | None = None,
    deal_id: str | None = None,
    is_garage_view: bool = False,
    allow_protected_photos: bool = False,
) -> dict[str, Any]:
    hero_assets = _load_assets(db, vin=vehicle.vin, tier=ImageTier.TIER2_HERO)
    tier3_assets = _load_assets(db, vin=vehicle.vin, tier=ImageTier.TIER3_PROCESSED)
    source_cache_assets = _load_assets(db, vin=vehicle.vin, tier=ImageTier.SOURCE_CACHE)

    hero_url = _asset_url(hero_assets[0]) if hero_assets else None
    tier3_gallery = [_asset_url(asset) for asset in tier3_assets if _asset_url(asset)]
    is_auction_source = bool(vehicle.source_type and vehicle.source_type.lower() in {"ove", "auction"})

    # Partition source cache assets by provider: EVOX > Imagin > source
    evox_assets = [asset for asset in source_cache_assets if asset.source_kind == EVOX_SOURCE_KIND]
    imagin_assets = [asset for asset in source_cache_assets if asset.source_kind == IMAGIN_SOURCE_KIND]
    source_assets = [
        asset for asset in source_cache_assets
        if asset.source_kind not in {IMAGIN_SOURCE_KIND, EVOX_SOURCE_KIND}
    ]

    # EVOX asset categories
    evox_card_gallery = [_asset_url(a) for a in evox_assets if _asset_url(a) and a.role in ("hero", "gallery")]
    evox_ext_stills = [_asset_url(a) for a in evox_assets if _asset_url(a) and a.role == "exterior_still"]
    evox_int_stills = [_asset_url(a) for a in evox_assets if _asset_url(a) and a.role == "interior_still"]
    evox_spin = [_asset_url(a) for a in evox_assets if _asset_url(a) and a.role == "spin"]
    evox_int_pano = [_asset_url(a) for a in evox_assets if _asset_url(a) and a.role == "interior_pano"]

    # Imagin assets (fallback)
    imagin_gallery = [_asset_url(asset) for asset in imagin_assets if _asset_url(asset) and asset.role != "spin"]
    spin_gallery = [_asset_url(asset) for asset in imagin_assets if _asset_url(asset) and asset.role == "spin"]
    source_gallery = [_asset_url(asset) for asset in source_assets if _asset_url(asset)]
    fallback_gallery = [str(url) for url in (vehicle.images or []) if str(url).strip()]

    # Filter out GIF/SVG from all galleries (UI elements scraped from auction sites)
    source_gallery = _filter_non_photo_urls(source_gallery)
    fallback_gallery = _filter_non_photo_urls(fallback_gallery)

    is_marketcheck_source = bool(
        vehicle.source_type and vehicle.source_type.lower() in {"marketcheck", "dealer_wholesale"}
    )

    # EVOX lazy-fetch: if no cached EVOX assets, signal frontend to trigger batch fetch
    evox_pending = not evox_card_gallery and settings.has_evox

    # Generate Imagin manifest as fallback if no cached Imagin (always available as instant base)
    manifest = None
    if not imagin_gallery:
        manifest = build_imagin_manifest(vehicle)
        if manifest:
            imagin_gallery = manifest.gallery_urls
            spin_gallery = manifest.spin_urls

    # Reference gallery: EVOX (color-accurate) > Imagin (approximation)
    reference_gallery = evox_card_gallery or imagin_gallery
    reference_hero = reference_gallery[0] if reference_gallery else None
    uses_evox = bool(evox_card_gallery)
    uses_imagin_for_ref = bool(imagin_gallery) and not uses_evox

    # Merge EVOX spin with Imagin spin fallback
    reference_spin = evox_spin or spin_gallery

    imagin_hero = imagin_gallery[0] if imagin_gallery else (manifest.hero_url if manifest else None)

    protected_photo_access = bool(allow_protected_photos)
    protected_photo_gallery = _merge_unique(source_gallery, fallback_gallery)

    # Public VDPs should only show EVOX/Imagin/generated imagery.
    dealer_photos_gated = False
    if is_marketcheck_source:
        if protected_photo_access:
            marketing_gallery = _merge_unique(protected_photo_gallery, reference_gallery)
        else:
            marketing_gallery = reference_gallery
            dealer_photos_gated = bool(protected_photo_gallery)
    elif is_auction_source:
        if protected_photo_access:
            marketing_gallery = _merge_unique(reference_gallery, protected_photo_gallery)
        else:
            marketing_gallery = reference_gallery
            dealer_photos_gated = bool(protected_photo_gallery)
    else:
        marketing_gallery = tier3_gallery or source_gallery or fallback_gallery

    if tier3_gallery:
        marketing_gallery = tier3_gallery
        dealer_photos_gated = False

    inspection_report = _load_current_inspection_report(db, vin=vehicle.vin, deal_id=deal_id)
    inspection_images_all: list[str] = []
    disclosure_images_all: list[str] = []
    ove_gallery_images_all: list[str] = []
    condition_report: dict[str, Any] = {}
    buyer_protection: dict[str, Any] = {}
    inspection_status = InspectionStatus.NOT_STARTED

    # Check for OVE condition report if no inspection report exists
    ove_detail = None
    if not inspection_report and is_auction_source:
        ove_detail = db.get(OveVehicleDetail, vehicle.vin)
        if ove_detail and ove_detail.condition_report_json:
            condition_report = ove_detail.condition_report_json
            inspection_status = InspectionStatus.VERIFIED
            ove_gallery_images_all, inspection_images_all, disclosure_images_all = _partition_ove_detail_images(
                ove_detail.images_json or []
            )

    if inspection_report:
        inspection_status = inspection_report.inspection_status
        condition_report = inspection_report.normalized_report_json or {}
        buyer_protection = inspection_report.buyer_protection_json or {}
        report_images = db.scalars(
            select(VehicleInspectionImage)
            .where(
                VehicleInspectionImage.inspection_report_id == inspection_report.id,
                VehicleInspectionImage.active.is_(True),
            )
            .order_by(VehicleInspectionImage.display_order.asc(), VehicleInspectionImage.created_at.asc())
        ).all()
        for row in report_images:
            link = row.source_url or resolve_storage_url(row.storage_key)
            if not link:
                continue
            if row.image_type == "disclosure":
                disclosure_images_all.append(link)
            else:
                inspection_images_all.append(link)

    inspection_images = inspection_images_all if protected_photo_access else []
    disclosure_images = disclosure_images_all if protected_photo_access else []
    if not protected_photo_access and (inspection_images_all or disclosure_images_all):
        dealer_photos_gated = True

    if protected_photo_access and ove_gallery_images_all:
        marketing_gallery = _merge_unique(marketing_gallery, ove_gallery_images_all)

    is_inspection_ready = (
        inspection_report is not None
        and inspection_status in READY_INSPECTION_STATUSES
        and len(inspection_images_all) > 0
    )
    is_inspection_ready_visible = is_inspection_ready and protected_photo_access
    is_inspection_stage = bool(deal_stage and deal_stage in INSPECTION_DRIVEN_STATES)
    is_inspection_pending = is_inspection_stage and not is_inspection_ready
    uses_imagin_stock = bool(imagin_gallery)
    uses_reference_stock = uses_evox or uses_imagin_for_ref

    # Preferred hero: EVOX > Imagin > processed hero > first marketing image
    preferred_hero = hero_url or reference_hero or imagin_hero or (marketing_gallery[0] if marketing_gallery else None)

    if is_inspection_ready_visible:
        mode = ImageDisplayMode.INSPECTION_REPORT
        if is_auction_source and marketing_gallery:
            hero_image = preferred_hero or (inspection_images[0] if inspection_images else None)
            gallery_images = _merge_unique(marketing_gallery, inspection_images)
        else:
            hero_image = inspection_images[0] if inspection_images else hero_url
            gallery_images = inspection_images
    elif is_inspection_pending:
        mode = ImageDisplayMode.INSPECTION_PENDING
        hero_image = preferred_hero or (marketing_gallery[0] if marketing_gallery else None)
        gallery_images = marketing_gallery
        if inspection_status == InspectionStatus.NOT_STARTED:
            inspection_status = InspectionStatus.PENDING

        if not hero_image and is_auction_source:
            hero_image = "/assets/images/portfolio/VCH Auction default image.webp"
    else:
        mode = ImageDisplayMode.MARKETING
        hero_image = preferred_hero or (marketing_gallery[0] if marketing_gallery else None)
        gallery_images = marketing_gallery

        if not hero_image and is_auction_source:
            hero_image = "/assets/images/portfolio/VCH Auction default image.webp"

    # Build disclaimer based on image source
    disclaimer = (
        "Reference photos may not reflect exact current condition. "
        "Use the inspection report for verified condition details."
    )
    if uses_evox:
        evox_meta = evox_assets[0].metadata_json if evox_assets else {}
        disclaimer = "EVOX factory reference images based on the vehicle's build specification."
        if evox_meta.get("match_level") == "model":
            disclaimer += " Trim-level details may vary from the actual vehicle."
        if not evox_meta.get("color_match_exact"):
            disclaimer += " Exterior color is approximate — exact paint code not available from source."
    elif uses_imagin_stock:
        disclaimer = (
            "IMAGIN studio reference images are generated from the auction listing spec. "
            "Inspection photos are appended after the condition report is ingested."
        )
        if manifest and not manifest.metadata.get("has_exact_exterior_color"):
            disclaimer += " Exterior color may be approximate until exact option codes are available."
        if manifest and not manifest.metadata.get("has_exact_interior_color"):
            disclaimer += " Interior trim and color may be approximate until exact option codes are available."

    # Determine EVOX color match exactness
    evox_color_exact = False
    if evox_assets:
        evox_color_exact = any(
            a.metadata_json and a.metadata_json.get("color_match_exact") for a in evox_assets
        )

    # Count real dealer photos that are hidden behind Garage auth
    gated_photo_count = 0
    if dealer_photos_gated:
        gated_photo_count = len(source_gallery) + len(fallback_gallery) + len(inspection_images_all) + len(disclosure_images_all)

    # Reference photos label
    if uses_evox:
        ref_label = "EVOX Factory Reference Images"
    elif uses_imagin_stock:
        ref_label = "IMAGIN Studio Reference Images"
    else:
        ref_label = "Reference Photos"

    return {
        "mode": mode.value,
        "inspection_status": inspection_status.value,
        "hero_image": hero_image,
        "gallery_images": gallery_images,
        "marketing_images": marketing_gallery,
        "imagin_images": imagin_gallery,
        "spin_images": reference_spin,
        "source_images": source_gallery if protected_photo_access else [],
        "inspection_images": inspection_images,
        "disclosure_images": disclosure_images,
        # EVOX detail-level assets (populated when full sync has run)
        "evox_exterior_stills": evox_ext_stills,
        "evox_interior_stills": evox_int_stills,
        "evox_spin_images": evox_spin,
        "evox_interior_pano": evox_int_pano,
        "has_evox_stock": uses_evox,
        "evox_pending": evox_pending,
        "evox_color_exact": evox_color_exact,
        # Existing flags
        "has_tier2_hero": bool(hero_assets),
        "has_tier3_processed": bool(tier3_assets),
        "has_inspection_report": inspection_report is not None or (ove_detail and bool(ove_detail.condition_report_json)),
        "has_imagin_stock": uses_imagin_stock,
        "dealer_photos_gated": dealer_photos_gated,
        "gated_photo_count": gated_photo_count,
        "protected_photo_access": protected_photo_access,
        "condition_report": condition_report,
        "buyer_protection": buyer_protection,
        "labels": {
            "inspection_primary": "Independent Inspection by Auction Platform",
            "reference_photos": ref_label,
        },
        "disclaimer": disclaimer,
    }


def _load_assets(db: Session, *, vin: str, tier: ImageTier) -> list[VehicleImageAsset]:
    return db.scalars(
        select(VehicleImageAsset)
        .where(
            VehicleImageAsset.vin == vin,
            VehicleImageAsset.tier == tier,
            VehicleImageAsset.active.is_(True),
        )
        .order_by(
            VehicleImageAsset.is_primary.desc(),
            VehicleImageAsset.display_order.asc(),
            VehicleImageAsset.created_at.asc(),
        )
    ).all()


def _load_current_inspection_report(
    db: Session,
    *,
    vin: str,
    deal_id: str | None,
) -> VehicleInspectionReport | None:
    stmt = select(VehicleInspectionReport).where(
        VehicleInspectionReport.vin == vin,
        VehicleInspectionReport.is_current.is_(True),
    )
    if deal_id:
        stmt = stmt.order_by(
            (VehicleInspectionReport.deal_id == deal_id).desc(),
            VehicleInspectionReport.normalized_at.desc(),
            VehicleInspectionReport.ingested_at.desc(),
            VehicleInspectionReport.updated_at.desc(),
        )
    else:
        stmt = stmt.order_by(
            VehicleInspectionReport.normalized_at.desc(),
            VehicleInspectionReport.ingested_at.desc(),
            VehicleInspectionReport.updated_at.desc(),
        )
    return db.scalar(stmt.limit(1))


def _asset_url(asset: VehicleImageAsset) -> str | None:
    return asset.external_url or resolve_storage_url(asset.storage_key)


def _fingerprint(*, vin: str, tier: ImageTier, payload: list[str]) -> str:
    joined = "|".join(payload)
    text = f"{vin}:{tier.value}:{joined}"
    return sha256(text.encode("utf-8")).hexdigest()


def _merge_unique(*groups: list[str]) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for group in groups:
        for url in group:
            if not url or url in seen:
                continue
            seen.add(url)
            merged.append(url)
    return merged
