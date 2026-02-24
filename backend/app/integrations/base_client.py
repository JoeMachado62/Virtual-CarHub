from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from app.core.retry import CircuitBreaker, CircuitBreakerOpenError, CircuitBreakerPolicy, with_retry


@dataclass(slots=True)
class ServicePolicy:
    max_retries: int
    timeout_seconds: float
    failure_threshold: int
    recovery_seconds: int


class ExternalServiceClient:
    def __init__(self, *, base_url: str, headers: dict[str, str] | None, policy: ServicePolicy):
        self.base_url = base_url.rstrip("/")
        self.headers = headers or {}
        self.policy = policy
        self.breaker = CircuitBreaker(
            CircuitBreakerPolicy(
                failure_threshold=policy.failure_threshold,
                recovery_seconds=policy.recovery_seconds,
            )
        )

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        if not self.breaker.allow():
            raise CircuitBreakerOpenError(f"Circuit breaker open for {self.base_url}")

        @with_retry(max_retries=self.policy.max_retries, timeout_label=self.base_url)
        def _do_request() -> Any:
            with httpx.Client(timeout=self.policy.timeout_seconds, headers=self.headers) as client:
                response = client.request(method, f"{self.base_url}{path}", **kwargs)
                response.raise_for_status()
                return response.json() if response.content else {}

        try:
            result = _do_request()
            self.breaker.mark_success()
            return result
        except Exception:
            self.breaker.mark_failure()
            raise
