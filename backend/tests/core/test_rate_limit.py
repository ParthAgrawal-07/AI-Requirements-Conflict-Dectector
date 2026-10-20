"""The fixed-window rate limiter used by sign-up (NFR-35)."""

import time
from typing import Any

import pytest
import redis

from app.core.rate_limit import (
    FallbackRateLimiter,
    InMemoryRateLimiter,
    RateLimitUnavailableError,
    RedisRateLimiter,
    TooManyRequestsError,
    client_ip,
    enforce,
)


class FakeRedis:
    """Just enough of redis-py's pipeline for the limiter; counts per key like INCR does."""

    def __init__(self) -> None:
        self.counts: dict[str, int] = {}
        self.expiries: dict[str, int] = {}

    def pipeline(self) -> "FakeRedis":
        self._queued: list[tuple[str, str, int | None]] = []
        return self

    def incr(self, key: str) -> None:
        self._queued.append(("incr", key, None))

    def expire(self, key: str, seconds: int) -> None:
        self._queued.append(("expire", key, seconds))

    def execute(self) -> list[Any]:
        results: list[Any] = []
        for op, key, arg in self._queued:
            if op == "incr":
                self.counts[key] = self.counts.get(key, 0) + 1
                results.append(self.counts[key])
            else:
                self.expiries[key] = arg or 0
                results.append(True)
        return results


@pytest.mark.parametrize("make", [InMemoryRateLimiter, lambda: RedisRateLimiter(FakeRedis())])
def test_allows_up_to_the_limit_then_reports_the_wait(make: Any) -> None:
    limiter = make()
    results = [limiter.hit("k", limit=3, window_seconds=60) for _ in range(5)]
    assert results[:3] == [None, None, None]
    assert all(isinstance(wait, int) and 1 <= wait <= 60 for wait in results[3:])


@pytest.mark.parametrize("make", [InMemoryRateLimiter, lambda: RedisRateLimiter(FakeRedis())])
def test_keys_are_independent(make: Any) -> None:
    limiter = make()
    assert limiter.hit("a", limit=1, window_seconds=60) is None
    assert limiter.hit("a", limit=1, window_seconds=60) is not None
    assert limiter.hit("b", limit=1, window_seconds=60) is None


def test_a_new_window_starts_a_new_count(monkeypatch: pytest.MonkeyPatch) -> None:
    limiter = InMemoryRateLimiter()
    clock = [1_000_020]
    monkeypatch.setattr(time, "time", lambda: clock[0])
    assert limiter.hit("k", limit=1, window_seconds=60) is None
    assert limiter.hit("k", limit=1, window_seconds=60) is not None
    clock[0] += 60
    assert limiter.hit("k", limit=1, window_seconds=60) is None


def test_the_redis_key_expires_with_its_window() -> None:
    fake = FakeRedis()
    RedisRateLimiter(fake).hit("signup:ip:1.2.3.4", limit=5, window_seconds=60)  # type: ignore[arg-type]
    ((key, seconds),) = fake.expiries.items()
    assert key.startswith("ratelimit:signup:ip:1.2.3.4:") and seconds == 60


def test_if_redis_is_down_the_limiter_fails_closed() -> None:
    class Down:
        def pipeline(self) -> "Down":
            return self

        def incr(self, _key: str) -> None: ...

        def expire(self, _key: str, _seconds: int) -> None: ...

        def execute(self) -> list[Any]:
            raise redis.ConnectionError("connection refused")

    with pytest.raises(RateLimitUnavailableError) as raised:
        RedisRateLimiter(Down()).hit("k", limit=5, window_seconds=60)  # type: ignore[arg-type]
    assert raised.value.status_code == 503


def test_enforce_raises_429_with_retry_after() -> None:
    limiter = InMemoryRateLimiter()
    enforce(limiter, "k", limit=1)
    with pytest.raises(TooManyRequestsError) as raised:
        enforce(limiter, "k", limit=1)
    assert raised.value.status_code == 429 and raised.value.code == "too_many_requests"
    assert 1 <= int(raised.value.headers["Retry-After"]) <= 60  # type: ignore[index]


def test_reset_clears_the_in_memory_counts() -> None:
    limiter = InMemoryRateLimiter()
    limiter.hit("k", limit=1, window_seconds=60)
    limiter.reset()
    assert limiter.hit("k", limit=1, window_seconds=60) is None


class DownRedis:
    """A Redis client whose every call fails, as when the server is unreachable."""

    def pipeline(self) -> "DownRedis":
        return self

    def incr(self, _key: str) -> None: ...

    def expire(self, _key: str, _seconds: int) -> None: ...

    def execute(self) -> list[Any]:
        raise redis.ConnectionError("connection refused")


def test_when_redis_is_down_limiting_continues_in_process_instead_of_blocking_everyone() -> None:
    """Redis being down must not take sign-up down (PR review #4): degrade, do not 503."""
    limiter = FallbackRateLimiter(RedisRateLimiter(DownRedis()), InMemoryRateLimiter())  # type: ignore[arg-type]

    results = [limiter.hit("signup:ip:1.2.3.4", limit=3, window_seconds=60) for _ in range(5)]

    assert results[:3] == [None, None, None]  # allowed, no exception
    assert all(wait is not None for wait in results[3:])  # and guessing is still limited


def test_the_fallback_uses_redis_when_it_is_healthy() -> None:
    fake = FakeRedis()
    fallback = InMemoryRateLimiter()
    limiter = FallbackRateLimiter(RedisRateLimiter(fake), fallback)  # type: ignore[arg-type]
    limiter.hit("k", limit=5, window_seconds=60)
    assert sum(fake.counts.values()) == 1
    assert fallback.hit("k", limit=1, window_seconds=60) is None  # untouched by the Redis path


def test_the_outage_warning_is_logged_once_per_minute_not_per_request() -> None:
    import logging

    class Collect(logging.Handler):
        def __init__(self) -> None:
            super().__init__(level=logging.WARNING)
            self.messages: list[str] = []

        def emit(self, record: logging.LogRecord) -> None:
            self.messages.append(record.getMessage())

    clock = [
        0.0
    ]  # a fresh host: monotonic time can be tiny, and the first warning must still appear
    limiter = FallbackRateLimiter(
        RedisRateLimiter(DownRedis()),  # type: ignore[arg-type]
        InMemoryRateLimiter(),
        clock=lambda: clock[0],
    )
    handler = Collect()
    logger = logging.getLogger("app.core.rate_limit")
    logger.addHandler(handler)
    previous = logger.level
    logger.setLevel(logging.WARNING)
    try:
        for _ in range(20):
            limiter.hit("k", limit=100, window_seconds=60)
        assert len(handler.messages) == 1
        clock[0] = 61.0  # a minute later the outage is worth mentioning again
        limiter.hit("k", limit=100, window_seconds=60)
        assert len(handler.messages) == 2
    finally:
        logger.removeHandler(handler)
        logger.setLevel(previous)


def test_the_default_limiter_is_the_redis_one_with_the_process_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core import rate_limit

    rate_limit._redis_limiter.cache_clear()
    monkeypatch.setattr(redis.Redis, "from_url", classmethod(lambda cls, *a, **k: DownRedis()))
    try:
        limiter = rate_limit.get_rate_limiter()
        assert isinstance(limiter, FallbackRateLimiter)
        assert limiter.hit("k", limit=1, window_seconds=60) is None  # outage tolerated
    finally:
        rate_limit._redis_limiter.cache_clear()


def _request(peer: str | None, forwarded: str | None = None) -> Any:
    from starlette.requests import Request

    headers = [(b"x-forwarded-for", forwarded.encode())] if forwarded is not None else []
    scope = {
        "type": "http",
        "headers": headers,
        "client": (peer, 1234) if peer else None,
        "method": "POST",
        "path": "/",
        "query_string": b"",
    }
    return Request(scope)


class TestClientIp:
    def test_without_a_trusted_proxy_the_socket_peer_is_used_and_the_header_ignored(self) -> None:
        assert client_ip(_request("10.0.0.5", "1.2.3.4"), trusted_hops=0) == "10.0.0.5"

    def test_one_trusted_proxy_means_the_rightmost_entry(self) -> None:
        assert client_ip(_request("10.0.0.5", "203.0.113.7"), trusted_hops=1) == "203.0.113.7"

    def test_entries_to_the_left_are_client_supplied_and_never_trusted(self) -> None:
        forwarded = "6.6.6.6, 203.0.113.7"  # the client claimed 6.6.6.6; the proxy saw 203.0.113.7
        assert client_ip(_request("10.0.0.5", forwarded), trusted_hops=1) == "203.0.113.7"

    def test_two_trusted_proxies_means_the_second_from_the_right(self) -> None:
        forwarded = "6.6.6.6, 203.0.113.7, 10.1.1.1"
        assert client_ip(_request("10.0.0.5", forwarded), trusted_hops=2) == "203.0.113.7"

    def test_a_missing_or_too_short_header_falls_back_to_the_peer(self) -> None:
        assert client_ip(_request("10.0.0.5"), trusted_hops=1) == "10.0.0.5"
        assert client_ip(_request("10.0.0.5", "203.0.113.7"), trusted_hops=2) == "10.0.0.5"

    def test_no_peer_at_all_is_unknown(self) -> None:
        assert client_ip(_request(None), trusted_hops=0) == "unknown"

    def test_the_setting_is_the_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.core.config import get_settings

        monkeypatch.setattr(get_settings(), "trusted_proxy_hops", 1)
        assert client_ip(_request("10.0.0.5", "198.51.100.1")) == "198.51.100.1"
