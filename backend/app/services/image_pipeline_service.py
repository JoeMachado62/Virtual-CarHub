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
    Vehicle,
    VehicleImageAsset,
    VehicleImageJob,
    VehicleInspectionImage,
    VehicleInspectionReport,
)
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

    normalized = [str(url).strip() for url in image_urls if str(url).strip()]
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
) -> VehicleCardMedia:
    context = resolve_vehicle_display_context(
        db,
        vehicle=vehicle,
        deal_stage=deal_stage,
        deal_id=deal_id,
    )
    return VehicleCardMedia(
        thumbnail=context.get("hero_image"),
        display_mode=ImageDisplayMode(context["mode"]),
        inspection_status=InspectionStatus(context["inspection_status"]),
        has_inspection_report=bool(context.get("has_inspection_report")),
    )


def resolve_vehicle_display_context(
    db: Session,
    *,
    vehicle: Vehicle,
    deal_stage: DealState | None = None,
    deal_id: str | None = None,
) -> dict[str, Any]:
    hero_assets = _load_assets(db, vin=vehicle.vin, tier=ImageTier.TIER2_HERO)
    tier3_assets = _load_assets(db, vin=vehicle.vin, tier=ImageTier.TIER3_PROCESSED)
    source_cache_assets = _load_assets(db, vin=vehicle.vin, tier=ImageTier.SOURCE_CACHE)

    hero_url = _asset_url(hero_assets[0]) if hero_assets else None
    tier3_gallery = [_asset_url(asset) for asset in tier3_assets if _asset_url(asset)]
    source_gallery = [_asset_url(asset) for asset in source_cache_assets if _asset_url(asset)]
    fallback_gallery = [str(url) for url in (vehicle.images or []) if str(url).strip()]
    marketing_gallery = tier3_gallery or source_gallery or fallback_gallery

    inspection_report = _load_current_inspection_report(db, vin=vehicle.vin, deal_id=deal_id)
    inspection_images: list[str] = []
    disclosure_images: list[str] = []
    condition_report: dict[str, Any] = {}
    buyer_protection: dict[str, Any] = {}
    inspection_status = InspectionStatus.NOT_STARTED

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
                disclosure_images.append(link)
            else:
                inspection_images.append(link)

    is_inspection_ready = (
        inspection_report is not None
        and inspection_status in READY_INSPECTION_STATUSES
        and len(inspection_images) > 0
    )
    is_inspection_stage = bool(deal_stage and deal_stage in INSPECTION_DRIVEN_STATES)
    is_inspection_pending = is_inspection_stage and not is_inspection_ready

    if is_inspection_ready:
        mode = ImageDisplayMode.INSPECTION_REPORT
        hero_image = inspection_images[0] if inspection_images else hero_url
        gallery_images = inspection_images
    elif is_inspection_pending:
        mode = ImageDisplayMode.INSPECTION_PENDING
        hero_image = hero_url or (marketing_gallery[0] if marketing_gallery else None)
        gallery_images = marketing_gallery
        if inspection_status == InspectionStatus.NOT_STARTED:
            inspection_status = InspectionStatus.PENDING
    else:
        mode = ImageDisplayMode.MARKETING
        hero_image = hero_url or (marketing_gallery[0] if marketing_gallery else None)
        gallery_images = marketing_gallery

    return {
        "mode": mode.value,
        "inspection_status": inspection_status.value,
        "hero_image": hero_image,
        "gallery_images": gallery_images,
        "marketing_images": marketing_gallery,
        "inspection_images": inspection_images,
        "disclosure_images": disclosure_images,
        "has_tier2_hero": bool(hero_assets),
        "has_tier3_processed": bool(tier3_assets),
        "has_inspection_report": inspection_report is not None,
        "condition_report": condition_report,
        "buyer_protection": buyer_protection,
        "labels": {
            "inspection_primary": "Independent Inspection by Auction Platform",
            "reference_photos": "Reference Photos",
        },
        "disclaimer": (
            "Reference photos may not reflect exact current condition. "
            "Use the inspection report for verified condition details."
        ),
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
