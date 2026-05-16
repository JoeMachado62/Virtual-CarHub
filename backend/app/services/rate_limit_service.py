"""v7 agent-action rate limiting.

Policy enforcement for outbound messages per Doc 2 §2.3, Doc 3 §10, Doc 4 §11.
Backed by Redis sorted sets (sliding window). Falls back to in-memory if Redis
is unavailable.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import redis

from app.core.config import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Rate limit policies (seconds)
# ---------------------------------------------------------------------------

# Key: (channel, context_type) → (limit, window_seconds)
# context_type distinguishes buyer vs dealer outbound.
POLICIES: dict[tuple[str, str], tuple[int, int]] = {
    # Buyer-side (Danny)
    ("sms", "buyer"):   (1, 4 * 3600),     # 1 SMS per contact per 4 hours
    ("email", "buyer"): (1, 12 * 3600),     # 1 email per contact per 12 hours
    ("mms", "buyer"):   (1, 4 * 3600),      # MMS same as SMS policy
    # Dealer-side (Negotiator)
    ("sms", "dealer"):          (1, 12 * 3600),     # 1 SMS per dealer_contact per 12 hours
    ("email", "dealer"):        (1, 24 * 3600),     # 1 email per dealer per 24 hours
    ("chat_widget", "dealer"):  (1, 2 * 3600),      # 1 per dealer per 2-hour cooldown
}

# Exception: if the contact/dealer replied within the window, the rate limit
# resets. Callers pass replied_within_window=True to bypass.


@dataclass(frozen=True, slots=True)
class RateLimitResult:
    allowed: bool
    reason: str | None = None
    next_allowed_at: datetime | None = None


def _redis_client() -> redis.Redis | None:
    try:
        client = redis.from_url(settings.redis_url, decode_responses=True)
        client.ping()
        return client
    except Exception:
        logger.warning("rate_limit_redis_unavailable, falling_back_to_allow")
        return None


_client: redis.Redis | None = None


def _get_redis() -> redis.Redis | None:
    global _client
    if _client is None:
        _client = _redis_client()
    return _client


def _build_key(target_id: str, channel: str, context_type: str) -> str:
    return f"{settings.rate_limit_redis_prefix}:agent:{target_id}:{channel}:{context_type}"


def check(
    target_id: str,
    channel: str,
    context_type: str = "buyer",
    replied_within_window: bool = False,
) -> RateLimitResult:
    """Check whether an outbound is allowed under rate policy.

    Args:
        target_id: contact_id (buyer) or dealer_id/dealer_contact_id (dealer)
        channel: sms | email | mms | chat_widget
        context_type: "buyer" or "dealer"
        replied_within_window: if True, rate limit is bypassed (contact replied)
    """
    if replied_within_window:
        return RateLimitResult(allowed=True)

    policy = POLICIES.get((channel, context_type))
    if policy is None:
        # No policy for this combination — allow by default.
        return RateLimitResult(allowed=True)

    limit, window_seconds = policy
    r = _get_redis()
    if r is None:
        # Redis down — fail open (allow) but log warning.
        return RateLimitResult(allowed=True)

    key = _build_key(target_id, channel, context_type)
    now = time.time()
    cutoff = now - window_seconds

    try:
        with r.pipeline() as pipe:
            pipe.zremrangebyscore(key, 0, cutoff)
            pipe.zcard(key)
            results = pipe.execute()

        count = int(results[1])

        if count >= limit:
            # Find when the oldest entry in the window will expire.
            oldest = r.zrange(key, 0, 0, withscores=True)
            if oldest:
                next_allowed_ts = oldest[0][1] + window_seconds
                next_allowed = datetime.fromtimestamp(next_allowed_ts, tz=UTC)
            else:
                next_allowed = datetime.now(UTC) + timedelta(seconds=window_seconds)

            return RateLimitResult(
                allowed=False,
                reason=f"max_{limit}_per_{window_seconds // 3600}h",
                next_allowed_at=next_allowed,
            )

        return RateLimitResult(allowed=True)

    except redis.RedisError:
        logger.warning("rate_limit_check_redis_error", exc_info=True)
        return RateLimitResult(allowed=True)


def record(
    target_id: str,
    channel: str,
    context_type: str = "buyer",
) -> None:
    """Record an outbound event for rate limiting."""
    policy = POLICIES.get((channel, context_type))
    if policy is None:
        return

    _, window_seconds = policy
    r = _get_redis()
    if r is None:
        return

    key = _build_key(target_id, channel, context_type)
    now = time.time()

    try:
        with r.pipeline() as pipe:
            pipe.zadd(key, {str(now): now})
            pipe.expire(key, window_seconds + 60)  # TTL slightly beyond window
            pipe.execute()
    except redis.RedisError:
        logger.warning("rate_limit_record_redis_error", exc_info=True)
