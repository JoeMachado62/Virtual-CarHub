import logging
from hashlib import sha256
import time
from urllib.parse import urlsplit

from sqlalchemy import or_, select

from app.core.config import settings
from app.core.constants import ImageTier
from app.db.session import SessionLocal
from app.integrations.marketcheck_client import MarketCheckClient
from app.models.entities import BuyerProfile, Deal, User, VehicleImageAsset
from app.services.inventory_service import (
    cleanup_stale_marketcheck_inventory,
    ingest_marketcheck_inventory,
    run_marketcheck_daily_snapshot,
    seed_inventory,
)
from app.services.marketcheck_history_enrichment_service import run_history_enrichment_batch
from app.services.matching_service import run_matching
from app.tasks.celery_app import celery_app

logger = logging.getLogger("vch.tasks")


@celery_app.task(name="inventory.nightly_ingest")
def nightly_ingest() -> dict:
    with SessionLocal() as db:
        if settings.has_marketcheck:
            client = MarketCheckClient(
                api_key=settings.marketcheck_api_key,
                api_secret=settings.marketcheck_api_secret,
                api_base_url=settings.marketcheck_api_base_url,
                live=True,
            )
            report = ingest_marketcheck_inventory(db, client=client, limit=200)
            result = report.to_dict()
        else:
            inserted = seed_inventory(db)
            result = {"inserted": inserted, "mode": "mock-seed", "source": "mock"}
        db.commit()
    return result


@celery_app.task(name="inventory.marketcheck_snapshot")
def marketcheck_snapshot(states: list[str] | None = None) -> dict:
    if not settings.has_marketcheck:
        return {"status": "skipped", "reason": "marketcheck_disabled"}
    if not settings.marketcheck_snapshot_enabled:
        return {"status": "skipped", "reason": "snapshot_disabled"}

    client = MarketCheckClient(
        api_key=settings.marketcheck_api_key,
        api_secret=settings.marketcheck_api_secret,
        api_base_url=settings.marketcheck_api_base_url,
        live=True,
    )
    with SessionLocal() as db:
        return run_marketcheck_daily_snapshot(
            db,
            client=client,
            target_states=states or settings.snapshot_target_states,
            limit_per_state=settings.snapshot_max_per_state,
            min_dom=settings.snapshot_min_dom,
            min_year=settings.snapshot_min_year,
            min_miles=settings.snapshot_min_miles,
            max_miles=settings.snapshot_max_miles,
        )


@celery_app.task(name="inventory.marketcheck_stale_cleanup")
def marketcheck_stale_cleanup(dry_run: bool = False) -> dict:
    with SessionLocal() as db:
        result = cleanup_stale_marketcheck_inventory(
            db,
            stale_threshold_days=settings.marketcheck_stale_threshold_days,
            max_mark=settings.marketcheck_stale_cleanup_max_per_run,
            dry_run=dry_run,
        )
        if not dry_run:
            db.commit()
        return result


@celery_app.task(name="images.cache_to_s3_batch")
def cache_images_to_s3_batch(batch_size: int = 100) -> dict:
    from app.services.s3_service import S3ServiceError, cache_remote_image, object_storage_uploads_enabled

    if not object_storage_uploads_enabled():
        return {"status": "skipped", "reason": "s3_disabled", "processed": 0, "cached": 0, "failed": 0}

    with SessionLocal() as db:
        assets = db.scalars(
            select(VehicleImageAsset)
            .where(
                VehicleImageAsset.tier == ImageTier.SOURCE_CACHE,
                VehicleImageAsset.active.is_(True),
                VehicleImageAsset.external_url.isnot(None),
                VehicleImageAsset.external_url != "",
                or_(
                    VehicleImageAsset.storage_key.is_(None),
                    VehicleImageAsset.storage_key == "",
                ),
            )
            .order_by(VehicleImageAsset.created_at.asc())
            .limit(max(1, batch_size))
        ).all()

        cached = 0
        failed = 0
        for asset in assets:
            try:
                result = cache_remote_image(
                    source_url=asset.external_url,
                    key=_image_cache_key(asset),
                )
            except (S3ServiceError, ValueError):
                logger.debug("image_cache_to_s3_failed asset_id=%s vin=%s", asset.id, asset.vin, exc_info=True)
                failed += 1
                continue

            asset.storage_key = result.storage_key
            asset.sha256 = result.sha256
            normalized = dict(asset.metadata_json or {})
            normalized["s3_cached_at"] = time.time()
            normalized["s3_content_type"] = result.content_type
            normalized["s3_size_bytes"] = result.size_bytes
            asset.metadata_json = normalized
            cached += 1

        db.commit()

    return {"status": "ok", "processed": len(assets), "cached": cached, "failed": failed}


def _image_cache_key(asset: VehicleImageAsset) -> str:
    url_hash = sha256(str(asset.external_url or "").encode("utf-8")).hexdigest()
    path = urlsplit(str(asset.external_url or "")).path.lower()
    ext = ".jpg"
    for candidate in (".jpg", ".jpeg", ".png", ".webp", ".avif"):
        if path.endswith(candidate):
            ext = ".jpg" if candidate == ".jpeg" else candidate
            break
    source = str(asset.source_kind or "source").strip().lower().replace("/", "-") or "source"
    return f"images/vehicles/{asset.vin}/{source}/{url_hash[:20]}{ext}"


@celery_app.task(name="matching.rerun_all")
def rerun_all_matching() -> dict:
    with SessionLocal() as db:
        profiles = db.scalars(select(BuyerProfile)).all()
        runs = 0
        for profile in profiles:
            deal = db.scalar(select(Deal).where(Deal.user_id == profile.user_id).order_by(Deal.created_at.desc()).limit(1))
            if not deal:
                continue
            run_matching(db, profile=profile, deal=deal)
            runs += 1
        db.commit()
    return {"runs": runs}


@celery_app.task(name="sync.ghl_reconcile")
def ghl_reconcile() -> dict:
    """Pull current contact state from GHL for every linked user and apply to VCH."""
    from app.services.ghl_lifecycle_service import GHLLifecycleService

    if not settings.has_ghl:
        return {"status": "skipped", "reason": "ghl_disabled"}

    lifecycle = GHLLifecycleService()
    results: list[dict] = []
    errors: list[dict] = []

    with SessionLocal() as db:
        users = db.scalars(
            select(User).where(User.ghl_contact_id.isnot(None))
        ).all()

        for user in users:
            try:
                result = lifecycle.reconcile_contact_from_ghl(db, user=user)
                if result.get("updated"):
                    results.append(result)
            except Exception as exc:
                logger.warning("ghl_reconcile failed for user %s: %s", user.id, exc)
                errors.append({"user_id": user.id, "error": str(exc)})
            time.sleep(0.6)  # stay under GHL 100 req/min rate limit

        db.commit()

    return {
        "status": "completed",
        "users_checked": len(users),
        "users_updated": len(results),
        "errors": len(errors),
        "updates": results[:20],
        "error_details": errors[:10],
    }


@celery_app.task(name="inventory.chromedata_backfill")
def chromedata_backfill(vins: list[str]) -> dict:
    """Fetch ChromeData factory images for a batch of VINs in the background."""
    if not settings.has_chromedata_media:
        return {"status": "skipped", "reason": "chromedata_disabled"}

    from app.services.chromedata_service import build_chromedata_manifest, sync_chromedata_source_assets
    from app.models.entities import Vehicle

    synced = 0
    skipped = 0
    failed = 0
    with SessionLocal() as db:
        for vin in vins:
            try:
                vehicle = db.get(Vehicle, vin)
                if not vehicle:
                    skipped += 1
                    continue
                manifest = build_chromedata_manifest(vehicle, detail_level="card")
                if manifest:
                    sync_chromedata_source_assets(db, vehicle=vehicle, manifest=manifest)
                    synced += 1
                else:
                    skipped += 1
            except Exception:
                logger.debug("chromedata_backfill failed for vin=%s", vin, exc_info=True)
                failed += 1
        db.commit()
    return {"synced": synced, "skipped": skipped, "failed": failed}


@celery_app.task(name="inventory.history_enrichment_batch")
def history_enrichment_batch(limit: int = 8, force: bool = False) -> dict:
    with SessionLocal() as db:
        result = run_history_enrichment_batch(db, limit=limit, force=force)
    return result
