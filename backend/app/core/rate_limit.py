"""Token-bucket API rate limiter.

Provides per-client rate limiting using an in-memory token bucket
algorithm.  In a distributed deployment, this should be replaced
with a Redis-backed limiter (see ``RedisRateLimiter`` below).

Usage in FastAPI routes (via dependency injection):

    from app.core.rate_limit import RateLimiterDependency

    @router.post("/orders", dependencies=[Depends(RateLimiterDependency())])
    async def create_order(...):
        ...
"""

from __future__ import annotations

import time
import threading
from typing import Any

from fastapi import HTTPException, Request, status

from app.core.config import settings


class TokenBucket:
    """In-memory token bucket for a single client."""

    __slots__ = ("capacity", "refill_rate", "_tokens", "_last_refill", "_lock")

    def __init__(self, capacity: int, refill_rate: float):
        self.capacity = capacity
        self.refill_rate = refill_rate  # tokens per second
        self._tokens = float(capacity)
        self._last_refill = time.monotonic()
        self._lock = threading.Lock()

    def consume(self, tokens: int = 1) -> bool:
        """Try to consume ``tokens`` from the bucket. Returns True on success."""
        with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_refill
            self._tokens = min(self.capacity, self._tokens + elapsed * self.refill_rate)
            self._last_refill = now
            if self._tokens >= tokens:
                self._tokens -= tokens
                return True
            return False


class InMemoryRateLimiter:
    """In-memory rate limiter keyed by client identifier."""

    def __init__(self, rpm: int = 120, burst: int = 20):
        self.rpm = rpm
        self.burst = burst
        self._buckets: dict[str, TokenBucket] = {}
        self._lock = threading.Lock()
        self._cleanup_counter = 0

    def _get_or_create(self, client_id: str) -> TokenBucket:
        with self._lock:
            bucket = self._buckets.get(client_id)
            if bucket is None:
                bucket = TokenBucket(capacity=self.burst, refill_rate=self.rpm / 60.0)
                self._buckets[client_id] = bucket
            # Periodic cleanup of stale buckets (every 1000 requests)
            self._cleanup_counter += 1
            if self._cleanup_counter >= 1000:
                self._cleanup()
            return bucket

    def _cleanup(self) -> None:
        """Remove stale buckets (not accessed in last 5 minutes)."""
        now = time.monotonic()
        stale_keys = [
            key for key, bucket in self._buckets.items()
            if now - bucket._last_refill > 300  # 5 minutes
        ]
        for key in stale_keys:
            del self._buckets[key]
        self._cleanup_counter = 0

    def allow(self, client_id: str) -> bool:
        bucket = self._get_or_create(client_id)
        return bucket.consume(1)


class RedisRateLimiter:
    """Redis-backed distributed rate limiter using sliding window."""

    def __init__(self, redis_url: str, rpm: int = 120, burst: int = 20):
        self.redis_url = redis_url
        self.rpm = rpm
        self.burst = burst
        self._redis: Any = None

    async def _get_redis(self):
        if self._redis is None:
            import redis.asyncio as aioredis
            self._redis = aioredis.from_url(self.redis_url)
        return self._redis

    async def allow(self, client_id: str) -> bool:
        import time
        r = await self._get_redis()
        key = f"ratelimit:{client_id}"
        now = int(time.time())
        window = 60  # 1 minute window

        pipe = r.pipeline()
        pipe.zremrangebyscore(key, 0, now - window)
        pipe.zadd(key, {str(now): now})
        pipe.zcount(key, now - window, now)
        pipe.expire(key, window)
        results = await pipe.execute()
        count = results[2]
        return count <= self.rpm


# Global limiter instance
_limiter: InMemoryRateLimiter | RedisRateLimiter | None = None


def get_rate_limiter() -> InMemoryRateLimiter | RedisRateLimiter | None:
    global _limiter
    if not settings.rate_limit_enabled:
        return None
    if _limiter is None:
        if settings.redis_url and settings.event_backend == "redis":
            # Use Redis-backed limiter in distributed mode
            _limiter = RedisRateLimiter(
                settings.redis_url,
                rpm=settings.rate_limit_rpm,
                burst=settings.rate_limit_burst,
            )
        else:
            _limiter = InMemoryRateLimiter(
                rpm=settings.rate_limit_rpm,
                burst=settings.rate_limit_burst,
            )
    return _limiter


def _get_client_id(request: Request) -> str:
    """Extract a client identifier from the request."""
    # Prefer API key (authenticated client)
    user = getattr(getattr(request, "state", None), "user", None)
    if user and user.get("sub"):
        return f"user:{user['sub']}"
    # Fall back to IP address
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return f"ip:{forwarded.split(',')[0].strip()}"
    return f"ip:{request.client.host if request.client else 'unknown'}"


async def rate_limit_dependency(request: Request) -> None:
    """FastAPI dependency: check rate limit and raise 429 if exceeded."""
    limiter = get_rate_limiter()
    if limiter is None:
        return

    client_id = _get_client_id(request)

    if isinstance(limiter, RedisRateLimiter):
        allowed = await limiter.allow(client_id)
    else:
        allowed = limiter.allow(client_id)

    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "error": {
                    "code": "RATE_LIMITED",
                    "message": f"Rate limit exceeded. Max {settings.rate_limit_rpm} requests per minute.",
                    "retry_after": 60,
                }
            },
        )
