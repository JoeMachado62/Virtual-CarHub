from celery import Celery
from celery.schedules import crontab

from app.core.config import settings

celery_app = Celery("virtual_carhub", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    beat_schedule={
        "ghl-reconcile-every-15m": {
            "task": "sync.ghl_reconcile",
            "schedule": 900.0,
        },
        "images-cache-to-s3-every-10m": {
            "task": "images.cache_to_s3_batch",
            "schedule": 600.0,
            "kwargs": {"batch_size": 200},
        },
        "inventory-marketcheck-snapshot-3am": {
            "task": "inventory.marketcheck_snapshot",
            "schedule": crontab(hour=3, minute=0),
        },
        "inventory-marketcheck-stale-cleanup-4am": {
            "task": "inventory.marketcheck_stale_cleanup",
            "schedule": crontab(hour=4, minute=0),
        },
    },
)
