from __future__ import annotations

import logging
import time
import uuid

from fastapi import Request
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.responses import err
from app.middleware.rate_limit import rate_limiter
from app.observability.metrics import record_rate_limit_block, record_request

logger = logging.getLogger("vch.http")


def _request_identity(request: Request) -> tuple[str, int]:
    service_token = request.headers.get("x-service-token")
    auth = request.headers.get("authorization")
    client_host = request.client.host if request.client else "unknown"

    if service_token:
        return f"agent:{client_host}", settings.agent_rate_limit_per_minute
    if auth:
        token_fingerprint = auth[-16:]
        return f"buyer:{token_fingerprint}:{client_host}", settings.buyer_rate_limit_per_minute
    return f"public:{client_host}", settings.buyer_rate_limit_per_minute


async def request_context_middleware(request: Request, call_next):  # type: ignore[no-untyped-def]
    request_id = request.headers.get("x-request-id", str(uuid.uuid4()))
    request.state.request_id = request_id

    key, limit = _request_identity(request)
    limit_result = rate_limiter.check(key=key, limit=limit, window_seconds=60)

    if not limit_result.allowed:
        scope = "agent" if key.startswith("agent:") else "buyer"
        record_rate_limit_block(scope=scope)
        response = JSONResponse(
            status_code=429,
            content=err("rate_limit_exceeded", "Too many requests", {"request_id": request_id}),
        )
        response.headers["X-Request-Id"] = request_id
        response.headers["Retry-After"] = str(limit_result.reset_seconds)
        return response

    start = time.perf_counter()
    response = await call_next(request)
    duration_ms = (time.perf_counter() - start) * 1000

    response.headers["X-Request-Id"] = request_id
    response.headers["X-RateLimit-Limit"] = str(limit)
    response.headers["X-RateLimit-Remaining"] = str(limit_result.remaining)
    response.headers["X-RateLimit-Reset"] = str(limit_result.reset_seconds)
    response.headers["X-Response-Time-Ms"] = f"{duration_ms:.1f}"

    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"

    logger.info(
        "request_complete",
        extra={
            "request_id": request_id,
            "method": request.method,
            "path": request.url.path,
            "status_code": response.status_code,
            "duration_ms": round(duration_ms, 2),
        },
    )

    if duration_ms > 5000:
        logger.warning(
            "request_latency_spike",
            extra={
                "request_id": request_id,
                "path": request.url.path,
                "duration_ms": round(duration_ms, 2),
            },
        )

    record_request(
        method=request.method,
        path=request.url.path,
        status_code=response.status_code,
        duration_seconds=duration_ms / 1000.0,
    )

    return response
