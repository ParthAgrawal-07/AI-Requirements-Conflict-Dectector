"""Redis-backed distributed rate limiter (Sprint 1 US-25).

Enforces:
- 10 join attempts per 10 minutes per IP and user.
- Atomic Redis strategy via single-step Lua script (INCR + EXPIRE).
- Shared across application processes via central Redis instance.
- Trusted infrastructure IP resolution (avoids trusting spoofed X-Forwarded-For).
- Fail-safe / fail-open policy when Redis is unavailable.
"""

from __future__ import annotations

import logging
from typing import Annotated, Any

import redis
from fastapi import Depends, Request

from app.core.auth import CurrentUser
from app.core.config import get_settings
from app.core.errors import RateLimitExceededError

logger = logging.getLogger(__name__)

# Rate limit configuration: 10 attempts per 10 minutes (600s)
JOIN_RATE_LIMIT_MAX_ATTEMPTS = 10
JOIN_RATE_LIMIT_WINDOW_SECONDS = 600

# Atomic Lua script for rate limiting:
# Atomically increments counter and sets TTL on first increment.
# Returns {current_count, ttl_seconds}.
_ATOMIC_RATE_LIMIT_LUA = """
local current = redis.call('INCR', KEYS[1])
if current == 1 then
    redis.call('EXPIRE', KEYS[1], ARGV[1])
end
local ttl = redis.call('TTL', KEYS[1])
return {current, ttl}
"""

_redis_pool: redis.ConnectionPool | None = None


def get_redis_client() -> redis.Redis | None:
    """Acquire shared Redis client from global connection pool.

    Returns None if Redis connection fails on initialization.
    """
    global _redis_pool
    try:
        if _redis_pool is None:
            settings = get_settings()
            _redis_pool = redis.ConnectionPool.from_url(
                settings.redis_url,
                decode_responses=True,
                socket_timeout=2.0,
                socket_connect_timeout=2.0,
            )
        return redis.Redis(connection_pool=_redis_pool)
    except Exception as exc:
        logger.warning("Failed to initialize Redis client pool: %s", exc)
        return None


def get_client_ip(request: Request) -> str:
    """Extract client IP from trusted ASGI connection infrastructure.

    To prevent rate-limit bypass via header spoofing, arbitrary forwarding
    headers (such as X-Forwarded-For) are not trusted unless verified proxy
    middleware is active. Uses request.client.host as the authoritative source.
    """
    if request.client and request.client.host:
        return request.client.host
    return "127.0.0.1"


class JoinRateLimiter:
    """Atomic distributed rate limiter for join code redemptions."""

    def __init__(
        self,
        max_attempts: int = JOIN_RATE_LIMIT_MAX_ATTEMPTS,
        window_seconds: int = JOIN_RATE_LIMIT_WINDOW_SECONDS,
    ) -> None:
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds

    def check_limit(
        self,
        redis_conn: Any,
        key: str,
    ) -> None:
        """Atomically increment and check limit for a key using Redis Lua script.

        Raises:
            RateLimitExceededError: If current attempts exceed max_attempts.
        """
        if redis_conn is None:
            return

        try:
            # Execute atomic Lua script
            result = redis_conn.eval(
                _ATOMIC_RATE_LIMIT_LUA,
                1,
                key,
                str(self.window_seconds),
            )
            count, ttl = int(result[0]), int(result[1])
            if count > self.max_attempts:
                retry_after = max(1, ttl) if ttl > 0 else self.window_seconds
                raise RateLimitExceededError(
                    f"Too many join attempts. Maximum {self.max_attempts} attempts per "
                    f"{self.window_seconds // 60} minutes allowed.",
                    retry_after=retry_after,
                )
        except RateLimitExceededError:
            raise
        except (redis.RedisError, ConnectionError, TimeoutError, OSError) as exc:
            # Fail-safe policy: Log warning and fail open so network hiccups do not wedge authentication
            logger.warning(
                "Redis rate limiter unavailable (%s); failing open for availability", exc
            )

    def enforce(
        self,
        request: Request,
        user: CurrentUser,
        redis_conn: redis.Redis | None,
    ) -> None:
        """Enforce dual rate limit on both client IP and authenticated user identity."""
        if redis_conn is None:
            return

        client_ip = get_client_ip(request)
        user_id = str(user.id)

        # 1. Check IP-scoped rate limit
        ip_key = f"rcd:ratelimit:join:ip:{client_ip}"
        self.check_limit(redis_conn, ip_key)

        # 2. Check User-scoped rate limit
        user_key = f"rcd:ratelimit:join:user:{user_id}"
        self.check_limit(redis_conn, user_key)


_join_limiter = JoinRateLimiter()


def rate_limit_join(
    request: Request,
    user: CurrentUser,
    redis_conn: Annotated[redis.Redis | None, Depends(get_redis_client)] = None,
) -> None:
    """FastAPI dependency enforcing join-code rate limit on IP and User."""
    _join_limiter.enforce(request, user, redis_conn)
