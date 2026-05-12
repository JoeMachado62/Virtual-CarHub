import logging
import threading

from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.logging import setup_logging
from app.core.responses import ok
from app.db.init_db import init_db
from app.db.session import SessionLocal
from app.middleware.http_middleware import request_context_middleware
from app.observability.metrics import metrics_payload
from app.services.marketcheck_history_enrichment_service import run_history_enrichment_batch
from app.services.ove_inventory_service import (
    cleanup_stale_ove_inventory,
    deactivate_missing_zip_ove_inventory,
    prune_unavailable_ove_inventory,
)

logger = logging.getLogger(__name__)


def _check_alembic_at_head() -> None:
    """Compare the live DB's alembic_version against the latest revision on
    disk. Logs a CRITICAL warning if they differ — does not refuse to start,
    so a missed migration causes loud noise instead of downtime, but the
    operator must run ``alembic upgrade head`` to clear it.
    """
    try:
        from alembic.config import Config
        from alembic.runtime.migration import MigrationContext
        from alembic.script import ScriptDirectory

        cfg = Config("alembic.ini")
        script = ScriptDirectory.from_config(cfg)
        head_rev = script.get_current_head()

        from app.db.session import engine

        with engine.connect() as conn:
            ctx = MigrationContext.configure(conn)
            db_rev = ctx.get_current_revision()

        if db_rev != head_rev:
            logger.critical(
                "alembic_version_drift db_rev=%s head_rev=%s "
                "ACTION_REQUIRED=run_alembic_upgrade_head",
                db_rev,
                head_rev,
            )
        else:
            logger.info("alembic_version_check_ok rev=%s", db_rev)
    except Exception:
        logger.warning("alembic_version_check_failed", exc_info=True)


def create_app() -> FastAPI:
    setup_logging()
    app = FastAPI(
        title="Virtual-CarHub API",
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
        # Default Starlette behavior is to issue a 307 redirect when a
        # trailing slash mismatches a route. Many HTTP clients (notably
        # python-requests + httpx in some configs) drop the request body on
        # 307, so a POST to /detail/claim/ would arrive at /detail/claim
        # bodyless and 422. We disable the redirect and normalize the path
        # in middleware below instead.
        redirect_slashes=False,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def strip_trailing_slash(request, call_next):
        scope = request.scope
        path = scope.get("path", "")
        if len(path) > 1 and path.endswith("/"):
            scope["path"] = path.rstrip("/")
            raw_path = scope.get("raw_path")
            if isinstance(raw_path, bytes) and len(raw_path) > 1 and raw_path.endswith(b"/"):
                scope["raw_path"] = raw_path.rstrip(b"/")
        return await call_next(request)

    app.middleware("http")(request_context_middleware)

    @app.on_event("startup")
    def startup_event() -> None:
        # Schema is owned by alembic in staging/production. Calling
        # Base.metadata.create_all() in those environments silently creates
        # net-new tables without their migrations, which has caused alembic
        # version drift before (see 2026-04-08 incident). Only allow the
        # convenience init in local dev where the DB is throwaway.
        if settings.vch_env == "local":
            init_db()
        else:
            logger.info(
                "init_db_skipped vch_env=%s reason=managed_by_alembic",
                settings.vch_env,
            )
            _check_alembic_at_head()

        if settings.has_marketcheck and settings.marketcheck_history_enrichment_enabled:
            stop_event = threading.Event()

            def enrichment_worker() -> None:
                startup_delay = max(0, settings.marketcheck_history_enrichment_startup_delay_seconds)
                if stop_event.wait(startup_delay):
                    return
                while not stop_event.is_set():
                    try:
                        with SessionLocal() as db:
                            result = run_history_enrichment_batch(
                                db,
                                limit=settings.marketcheck_history_enrichment_batch_size,
                            )
                        if result.get("processed"):
                            logger.info("marketcheck_history_enrichment_batch %s", result)
                    except Exception:
                        logger.warning("marketcheck_history_enrichment_worker_failed", exc_info=True)

                    interval = max(60, settings.marketcheck_history_enrichment_interval_seconds)
                    if stop_event.wait(interval):
                        return

            thread = threading.Thread(
                target=enrichment_worker,
                name="marketcheck-history-enrichment",
                daemon=True,
            )
            app.state.marketcheck_history_enrichment_stop_event = stop_event
            app.state.marketcheck_history_enrichment_thread = thread
            thread.start()

        if settings.ove_stale_cleanup_enabled:
            ove_stop_event = threading.Event()

            def ove_stale_cleanup_worker() -> None:
                startup_delay = max(0, settings.ove_stale_cleanup_startup_delay_seconds)
                if ove_stop_event.wait(startup_delay):
                    return
                while not ove_stop_event.is_set():
                    try:
                        with SessionLocal() as db:
                            result = cleanup_stale_ove_inventory(
                                db,
                                stale_threshold_days=settings.ove_stale_threshold_days,
                                max_mark=settings.ove_stale_cleanup_max_per_run,
                            )
                            missing_zip_result = deactivate_missing_zip_ove_inventory(
                                db,
                                max_mark=settings.ove_stale_cleanup_max_per_run,
                            )
                            prune_result = prune_unavailable_ove_inventory(
                                db,
                                retention_days=settings.ove_unavailable_retention_days,
                                max_delete=settings.ove_unavailable_cleanup_max_per_run,
                            )
                            if (
                                result.get("marked_unavailable", 0) > 0
                                or missing_zip_result.get("marked_unavailable", 0) > 0
                                or prune_result.get("deleted", 0) > 0
                            ):
                                db.commit()
                                logger.info(
                                    "ove_stale_cleanup_worker marked %d stale vehicles, "
                                    "marked %d missing-zip vehicles, "
                                    "deleted %d unavailable OVE rows "
                                    "(remaining_stale=%d, remaining_missing_zip=%d, remaining_prunable=%d)",
                                    result.get("marked_unavailable"),
                                    missing_zip_result.get("marked_unavailable"),
                                    prune_result.get("deleted"),
                                    result.get("remaining_stale", 0),
                                    missing_zip_result.get("remaining_missing_zip", 0),
                                    prune_result.get("remaining_prunable", 0),
                                )
                    except Exception:
                        logger.warning("ove_stale_cleanup_worker_failed", exc_info=True)

                    interval = max(60, settings.ove_stale_cleanup_interval_seconds)
                    if ove_stop_event.wait(interval):
                        return

            ove_thread = threading.Thread(
                target=ove_stale_cleanup_worker,
                name="ove-stale-cleanup",
                daemon=True,
            )
            app.state.ove_stale_cleanup_stop_event = ove_stop_event
            app.state.ove_stale_cleanup_thread = ove_thread
            ove_thread.start()

    @app.on_event("shutdown")
    def shutdown_event() -> None:
        stop_event = getattr(app.state, "marketcheck_history_enrichment_stop_event", None)
        thread = getattr(app.state, "marketcheck_history_enrichment_thread", None)
        if stop_event is not None:
            stop_event.set()
        if thread is not None and thread.is_alive():
            thread.join(timeout=2)

        ove_stop_event = getattr(app.state, "ove_stale_cleanup_stop_event", None)
        ove_thread = getattr(app.state, "ove_stale_cleanup_thread", None)
        if ove_stop_event is not None:
            ove_stop_event.set()
        if ove_thread is not None and ove_thread.is_alive():
            ove_thread.join(timeout=2)

    @app.get("/health")
    def health() -> dict:
        return ok({"service": "virtual-carhub-api", "env": settings.vch_env})

    if settings.metrics_enabled:

        @app.get(settings.metrics_path)
        def metrics() -> Response:
            payload, content_type = metrics_payload()
            return Response(content=payload, media_type=content_type)

    app.include_router(api_router)
    return app


app = create_app()
