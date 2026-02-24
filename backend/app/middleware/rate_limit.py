from __future__ import annotations

import time
from collections import defaultdict, deque
from dataclasses import dataclass
from threading import Lock

import redis

from app.core.config import settings


@dataclass(slots=True)
class LimitResult:
    allowed: bool
    remaining: int
    reset_seconds: int


class RateLimiter:
    def __init__(self) -> None:
        self._memory: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()
        self._redis = self._create_redis_client()

    def _create_redis_client(self) -> redis.Redis | None:
        try:
            client = redis.from_url(settings.redis_url, decode_responses=True)
            client.ping()
            return client
        except Exception:
            return None

    def check(self, key: str, limit: int, window_seconds: int = 60) -> LimitResult:
        if self._redis:
            return self._check_redis(key, limit, window_seconds)
        return self._check_memory(key, limit, window_seconds)

    def _check_memory(self, key: str, limit: int, window_seconds: int) -> LimitResult:
        now = time.time()
        cutoff = now - window_seconds

        with self._lock:
            q = self._memory[key]
            while q and q[0] < cutoff:
                q.popleft()

            if len(q) >= limit:
                reset_seconds = max(1, int(window_seconds - (now - q[0])))
                return LimitResult(allowed=False, remaining=0, reset_seconds=reset_seconds)

            q.append(now)
            remaining = max(0, limit - len(q))
            reset_seconds = window_seconds
            return LimitResult(allowed=True, remaining=remaining, reset_seconds=reset_seconds)

    def _check_redis(self, key: str, limit: int, window_seconds: int) -> LimitResult:
        assert self._redis is not None
        bucket = f"{settings.rate_limit_redis_prefix}:{key}"
        now = time.time()
        cutoff = now - window_seconds

        with self._redis.pipeline() as pipe:
            pipe.zremrangebyscore(bucket, 0, cutoff)
            pipe.zcard(bucket)
            pipe.execute()

        count = int(self._redis.zcard(bucket))
        if count >= limit:
            oldest = self._redis.zrange(bucket, 0, 0, withscores=True)
            if oldest:
                reset_seconds = max(1, int(window_seconds - (now - oldest[0][1])))
            else:
                reset_seconds = window_seconds
            return LimitResult(allowed=False, remaining=0, reset_seconds=reset_seconds)

        with self._redis.pipeline() as pipe:
            pipe.zadd(bucket, {str(now): now})
            pipe.expire(bucket, window_seconds)
            pipe.execute()

        remaining = max(0, limit - (count + 1))
        return LimitResult(allowed=True, remaining=remaining, reset_seconds=window_seconds)


rate_limiter = RateLimiter()
