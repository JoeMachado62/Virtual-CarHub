import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from typing import TypeVar

from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

T = TypeVar("T")


@dataclass(slots=True)
class CircuitBreakerPolicy:
    failure_threshold: int
    recovery_seconds: int


class CircuitBreakerOpenError(RuntimeError):
    pass


class CircuitBreaker:
    def __init__(self, policy: CircuitBreakerPolicy):
        self.policy = policy
        self._failures: deque[float] = deque(maxlen=policy.failure_threshold)
        self._opened_at: float | None = None

    def _prune(self) -> None:
        if self._opened_at is None:
            return
        if time.time() - self._opened_at >= self.policy.recovery_seconds:
            self._opened_at = None
            self._failures.clear()

    def allow(self) -> bool:
        self._prune()
        return self._opened_at is None

    def mark_failure(self) -> None:
        now = time.time()
        self._failures.append(now)
        if len(self._failures) >= self.policy.failure_threshold:
            self._opened_at = now

    def mark_success(self) -> None:
        self._failures.clear()
        self._opened_at = None


def with_retry(max_retries: int, timeout_label: str = "service") -> Callable[[Callable[..., T]], Callable[..., T]]:
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @retry(
            stop=stop_after_attempt(max_retries),
            wait=wait_exponential(multiplier=1, min=1, max=8),
            retry=retry_if_exception_type(Exception),
            reraise=True,
        )
        def wrapped(*args, **kwargs):  # type: ignore[no-untyped-def]
            return func(*args, **kwargs)

        wrapped.__name__ = f"retry_{timeout_label}_{func.__name__}"
        return wrapped

    return decorator
