from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.logging import setup_logging
from app.core.responses import ok
from app.db.init_db import init_db
from app.middleware.http_middleware import request_context_middleware
from app.observability.metrics import metrics_payload


def create_app() -> FastAPI:
    setup_logging()
    app = FastAPI(
        title="Virtual-CarHub API",
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.middleware("http")(request_context_middleware)

    @app.on_event("startup")
    def startup_event() -> None:
        init_db()

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
