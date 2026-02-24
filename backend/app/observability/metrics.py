from __future__ import annotations

import logging

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

logger = logging.getLogger("vch.metrics")

REQUEST_COUNTER = Counter(
    "vch_http_requests_total",
    "Total HTTP requests",
    ["method", "path", "status_code"],
)

REQUEST_DURATION = Histogram(
    "vch_http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["method", "path"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10),
)

RATE_LIMIT_BLOCKS = Counter(
    "vch_http_rate_limit_blocks_total",
    "Requests blocked by rate limiter",
    ["scope"],
)

DEAL_STATE_TRANSITIONS = Counter(
    "vch_deal_state_transitions_total",
    "Deal state transitions",
    ["from_state", "to_state", "actor"],
)

EXTERNAL_SYNC_ERRORS = Counter(
    "vch_external_sync_errors_total",
    "External integration sync errors",
    ["provider", "operation"],
)


def record_request(method: str, path: str, status_code: int, duration_seconds: float) -> None:
    REQUEST_COUNTER.labels(method=method, path=path, status_code=str(status_code)).inc()
    REQUEST_DURATION.labels(method=method, path=path).observe(duration_seconds)


def record_rate_limit_block(scope: str) -> None:
    RATE_LIMIT_BLOCKS.labels(scope=scope).inc()


def record_state_transition(from_state: str, to_state: str, actor: str) -> None:
    DEAL_STATE_TRANSITIONS.labels(from_state=from_state, to_state=to_state, actor=actor).inc()


def record_external_sync_error(provider: str, operation: str) -> None:
    EXTERNAL_SYNC_ERRORS.labels(provider=provider, operation=operation).inc()


def metrics_payload() -> tuple[bytes, str]:
    data = generate_latest()
    return data, CONTENT_TYPE_LATEST
