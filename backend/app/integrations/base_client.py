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

    def _headers_for_request(self) -> dict[str, str]:
        return dict(self.headers)

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        if not self.breaker.allow():
            raise CircuitBreakerOpenError(f"Circuit breaker open for {self.base_url}")

        @with_retry(max_retries=self.policy.max_retries, timeout_label=self.base_url)
        def _do_request() -> Any:
            request_headers = self._headers_for_request()
            extra_headers = kwargs.pop("headers", None) or {}
            request_headers.update(extra_headers)
            with httpx.Client(timeout=self.policy.timeout_seconds, headers=request_headers) as client:
                response = client.request(method, f"{self.base_url}{path}", **kwargs)
                response.raise_for_status()
                return response.json() if response.content else {}

        try:
            result = _do_request()
            self.breaker.mark_success()
            return result
        except httpx.HTTPStatusError as exc:
            # 4xx = client error (not found, bad request, etc.) — the service
            # is reachable and responding.  Only 5xx (server errors) and
            # connection failures should trip the circuit breaker.
            if exc.response is not None and exc.response.status_code < 500:
                self.breaker.mark_success()
            else:
                self.breaker.mark_failure()
            raise
        except Exception:
            self.breaker.mark_failure()
            raise
