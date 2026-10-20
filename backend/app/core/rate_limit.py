"""Small fixed-window rate limiter (Parth — NFR-28, NFR-35).

Needed first by ``POST /auth/signup``, the one route where an *unauthenticated* caller can
guess join codes (5 attempts per minute per IP and per e-mail, NFR-35). Madhav's join-code
service can reuse it for ``POST /join`` — same interface, different key.

* ``RedisRateLimiter`` — production: ``INCR`` + ``EXPIRE`` on one key per (name, window).
* ``InMemoryRateLimiter`` — tests (and a safe default when nothing is injected in tests).

If Redis is unreachable the limiter **degrades to a per-process counter** (and logs a warning)
instead of blocking every sign-up: guessing is still limited, only less strictly with several
workers. Redis being down must not take sign-up down with it.
"""

import hashlib
import logging
import threading
import time
from collections.abc import Callable
from functools import lru_cache
from typing import Protocol

import redis
from fastapi import Request

from app.core.config import get_settings
from app.core.errors import AppError, ServiceUnavailableError

logger = logging.getLogger(__name__)


class TooManyRequestsError(AppError):
    status_code = 429
    code = "too_many_requests"

    def __init__(self, retry_after_seconds: int) -> None:
        super().__init__(
            "Too many attempts. Please wait a moment and try again.",
            headers={"Retry-After": str(max(1, retry_after_seconds))},
        )
        self.retry_after_seconds = retry_after_seconds


class RateLimitUnavailableError(ServiceUnavailableError):
    def __init__(self) -> None:
        super().__init__(
            "This action is temporarily unavailable. Please try again shortly.",
            code="rate_limit_unavailable",
        )


class RateLimiter(Protocol):
    def hit(self, key: str, *, limit: int, window_seconds: int) -> int | None:
        """Count one attempt. Returns ``None`` if allowed, else seconds until the window ends."""
        ...


def hash_key_part(value: str) -> str:
    """Keys must not contain raw e-mail addresses (they would end up in Redis and its logs)."""
    return hashlib.sha256(value.strip().lower().encode()).hexdigest()[:32]


class RedisRateLimiter:
    def __init__(self, client: redis.Redis) -> None:
        self._client = client

    def hit(self, key: str, *, limit: int, window_seconds: int) -> int | None:
        now = int(time.time())
        window = now // window_seconds
        redis_key = f"ratelimit:{key}:{window}"
        try:
            pipe = self._client.pipeline()
            pipe.incr(redis_key)
            pipe.expire(redis_key, window_seconds)
            count = int(pipe.execute()[0])
        except redis.RedisError:
            raise RateLimitUnavailableError() from None
        if count > limit:
            return (window + 1) * window_seconds - now
        return None


class InMemoryRateLimiter:
    """Process-local limiter for tests and single-process development."""

    def __init__(self) -> None:
        self._counts: dict[tuple[str, int], int] = {}
        self._lock = threading.Lock()

    def hit(self, key: str, *, limit: int, window_seconds: int) -> int | None:
        now = int(time.time())
        window = now // window_seconds
        with self._lock:
            count = self._counts.get((key, window), 0) + 1
            self._counts[(key, window)] = count
        return (window + 1) * window_seconds - now if count > limit else None

    def reset(self) -> None:
        with self._lock:
            self._counts.clear()


class FallbackRateLimiter:
    """Use ``primary`` (Redis); if it is unavailable, count in this process instead."""

    def __init__(
        self,
        primary: RateLimiter,
        fallback: RateLimiter,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._primary = primary
        self._fallback = fallback
        self._clock = clock
        self._warned_at: float | None = None  # None: not warned yet (never compare with 0.0)

    def hit(self, key: str, *, limit: int, window_seconds: int) -> int | None:
        try:
            return self._primary.hit(key, limit=limit, window_seconds=window_seconds)
        except RateLimitUnavailableError:
            now = self._clock()
            if (
                self._warned_at is None or now - self._warned_at > 60
            ):  # once a minute, not per request
                self._warned_at = now
                logger.warning("Redis unavailable: rate limiting falls back to this process only")
            return self._fallback.hit(key, limit=limit, window_seconds=window_seconds)


def client_ip(request: Request, trusted_hops: int | None = None) -> str:
    """The address rate limits should key on.

    With no trusted proxy (the default) this is the socket peer and ``X-Forwarded-For`` is
    ignored, because any client can forge it. Behind ``N`` trusted reverse proxies
    (``TRUSTED_PROXY_HOPS``), the N-th entry from the right is the address the outermost proxy
    saw — entries further left are client-supplied and are never trusted.
    """
    hops = get_settings().trusted_proxy_hops if trusted_hops is None else trusted_hops
    peer = request.client.host if request.client else "unknown"
    if hops <= 0:
        return peer
    forwarded = [
        part.strip()
        for part in request.headers.get("x-forwarded-for", "").split(",")
        if part.strip()
    ]
    return forwarded[-hops] if len(forwarded) >= hops else peer


_in_process_limiter = InMemoryRateLimiter()


@lru_cache
def _redis_limiter() -> FallbackRateLimiter:
    client = redis.Redis.from_url(
        get_settings().redis_url, socket_connect_timeout=2, socket_timeout=2
    )
    return FallbackRateLimiter(RedisRateLimiter(client), _in_process_limiter)


def get_rate_limiter() -> RateLimiter:
    """FastAPI dependency (override in tests with an :class:`InMemoryRateLimiter`)."""
    return _redis_limiter()


def enforce(limiter: RateLimiter, key: str, *, limit: int, window_seconds: int = 60) -> None:
    """Count an attempt and raise :class:`TooManyRequestsError` (429) if over the limit."""
    retry_after = limiter.hit(key, limit=limit, window_seconds=window_seconds)
    if retry_after is not None:
        raise TooManyRequestsError(retry_after)
