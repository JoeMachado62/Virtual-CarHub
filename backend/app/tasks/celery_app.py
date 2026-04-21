from celery import Celery

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
    },
)
