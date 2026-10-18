"""Tests for Redis distributed rate limiting (Sprint 1 US-25).

Covers:
- Atomic Lua increment and TTL tracking.
- Enforcement of 10 attempts per 10 minutes limit.
- 11th attempt raises RateLimitExceededError (HTTP 429) with Retry-After header.
- IP vs User dual-key isolation.
- Fail-open resilience when Redis is unreachable.
- Trusted infrastructure client IP resolution (ignoring unverified headers).
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi import Request

from app.core.errors import RateLimitExceededError
from app.core.rate_limit import (
    JoinRateLimiter,
    get_client_ip,
)
from app.models.enums import Role
from app.models.user import User


class FakeRedis:
    """In-memory mock reproducing Redis key-value storage and Lua eval behavior."""

    def __init__(self) -> None:
        self.store: dict[str, int] = {}
        self.ttls: dict[str, int] = {}

    def eval(self, script: str, numkeys: int, key: str, window_seconds: str) -> list[int]:
        ttl = int(window_seconds)
        if key not in self.store:
            self.store[key] = 1
            self.ttls[key] = ttl
        else:
            self.store[key] += 1
        return [self.store[key], self.ttls[key]]


class FailingRedis:
    """Mock simulating a disconnected or dead Redis cluster."""

    def eval(self, *args: Any, **kwargs: Any) -> Any:
        import redis

        raise redis.ConnectionError("Could not connect to Redis server: Connection refused")


# ── 1. Atomic Lua Script & Counter Limit Tests ────────────────────────────────


def test_atomic_rate_limiter_allows_up_to_max_attempts() -> None:
    fake_redis = FakeRedis()
    limiter = JoinRateLimiter(max_attempts=10, window_seconds=600)
    key = "test:ratelimit:ip:192.168.1.10"

    # Exactly 10 attempts must succeed
    for _ in range(10):
        limiter.check_limit(fake_redis, key)

    # 11th attempt must raise RateLimitExceededError
    with pytest.raises(RateLimitExceededError) as exc_info:
        limiter.check_limit(fake_redis, key)

    assert exc_info.value.status_code == 429
    assert exc_info.value.code == "too_many_requests"
    assert exc_info.value.headers is not None
    assert "Retry-After" in exc_info.value.headers
    assert int(exc_info.value.headers["Retry-After"]) > 0


# ── 2. Dual IP & User Key Isolation Tests ─────────────────────────────────────


def test_rate_limiter_enforces_ip_and_user_isolation() -> None:
    fake_redis = FakeRedis()
    limiter = JoinRateLimiter(max_attempts=10, window_seconds=600)

    user1 = User(
        id=uuid.uuid4(),
        email="user1@test.com",
        full_name="User 1",
        hashed_password="h",
        role=Role.READ_ONLY,
        workspace_id=uuid.uuid4(),
    )
    user2 = User(
        id=uuid.uuid4(),
        email="user2@test.com",
        full_name="User 2",
        hashed_password="h",
        role=Role.READ_ONLY,
        workspace_id=uuid.uuid4(),
    )

    req_ip1 = MagicMock(spec=Request)
    req_ip1.client = MagicMock()
    req_ip1.client.host = "10.0.0.1"

    req_ip2 = MagicMock(spec=Request)
    req_ip2.client = MagicMock()
    req_ip2.client.host = "10.0.0.2"

    # Exhaust user1 from IP 10.0.0.1
    for _ in range(10):
        limiter.enforce(req_ip1, user1, fake_redis)

    # 11th attempt for user1 from IP 10.0.0.1 fails
    with pytest.raises(RateLimitExceededError):
        limiter.enforce(req_ip1, user1, fake_redis)

    # Different user (user2) from a different IP (10.0.0.2) is NOT blocked
    limiter.enforce(req_ip2, user2, fake_redis)

    # Same user (user1) attempting from another IP is STILL blocked by user key
    with pytest.raises(RateLimitExceededError):
        limiter.enforce(req_ip2, user1, fake_redis)

    # Different user (user2) attempting from the exhausted IP is STILL blocked by IP key
    with pytest.raises(RateLimitExceededError):
        limiter.enforce(req_ip1, user2, fake_redis)


# ── 3. Fail-Open Policy When Redis is Unavailable ─────────────────────────────


def test_rate_limiter_fails_open_when_redis_unavailable() -> None:
    failing_redis = FailingRedis()
    limiter = JoinRateLimiter(max_attempts=10, window_seconds=600)
    key = "test:ratelimit:ip:10.0.0.1"

    # Must fail open (no exception raised, logs warning)
    limiter.check_limit(failing_redis, key)

    user = User(
        id=uuid.uuid4(),
        email="user@test.com",
        full_name="User",
        hashed_password="h",
        role=Role.READ_ONLY,
        workspace_id=uuid.uuid4(),
    )
    req = MagicMock(spec=Request)
    req.client = MagicMock()
    req.client.host = "10.0.0.1"

    # enforce must also fail open gracefully
    limiter.enforce(req, user, failing_redis)

    # None client must also fail open gracefully
    limiter.enforce(req, user, None)


# ── 4. Trusted Infrastructure Client IP Resolution ────────────────────────────


def test_get_client_ip_ignores_untrusted_forwarded_headers() -> None:
    req = MagicMock(spec=Request)
    req.client = MagicMock()
    req.client.host = "203.0.113.195"
    # Even if an attacker injects a fake X-Forwarded-For header:
    req.headers = {"X-Forwarded-For": "1.2.3.4, 5.6.7.8"}

    resolved_ip = get_client_ip(req)
    assert resolved_ip == "203.0.113.195"
    assert resolved_ip != "1.2.3.4"


def test_get_client_ip_fallback_when_client_missing() -> None:
    req = MagicMock(spec=Request)
    req.client = None
    assert get_client_ip(req) == "127.0.0.1"
