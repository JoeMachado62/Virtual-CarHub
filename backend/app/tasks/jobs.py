import logging
import time

from sqlalchemy import select

from app.core.config import settings
from app.db.session import SessionLocal
from app.integrations.marketcheck_client import MarketCheckClient
from app.models.entities import BuyerProfile, Deal, User
from app.services.inventory_service import ingest_marketcheck_inventory, seed_inventory
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
                price_api_key=settings.marketcheck_price_api_key,
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


@celery_app.task(name="inventory.history_enrichment_batch")
def history_enrichment_batch(limit: int = 8, force: bool = False) -> dict:
    with SessionLocal() as db:
        result = run_history_enrichment_batch(db, limit=limit, force=force)
    return result
