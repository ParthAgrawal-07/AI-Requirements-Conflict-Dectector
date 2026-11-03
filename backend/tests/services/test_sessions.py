"""Session stores (US-19): both implementations give the same answers.

The Redis store runs against the real Redis from ``REDIS_URL``; it is skipped when Redis is
unreachable, unless ``REQUIRE_DB=1`` (CI), where that is a failure.
"""

import os
import uuid
from collections.abc import Callable, Iterator
from unittest.mock import MagicMock

import pytest
import redis

from app.core.config import get_settings
from app.core.security import RefreshPayload, create_refresh_token
from app.services import sessions
from app.services.sessions import REUSE_GRACE_SECONDS, Use

Store = sessions.InMemorySessionStore | sessions.RedisSessionStore


def _payload(session_id: str | None = None) -> RefreshPayload:
    return create_refresh_token(uuid.uuid4(), session_id=session_id)[1]


@pytest.fixture(params=["memory", "redis"])
def clocked_store(request: pytest.FixtureRequest) -> Iterator[tuple[Store, list[float]]]:
    now = [1_000_000.0]
    if request.param == "memory":
        yield sessions.InMemorySessionStore(clock=lambda: now[0]), now
        return
    client = redis.Redis.from_url(get_settings().redis_url, socket_connect_timeout=1)
    try:
        client.ping()
    except redis.RedisError as exc:
        if os.environ.get("REQUIRE_DB") == "1":
            pytest.fail(f"Redis is not reachable: {exc}")
        pytest.skip(f"Redis is not reachable: {exc}")
    yield sessions.RedisSessionStore(client, clock=lambda: now[0]), now
    client.close()


def test_first_use_then_grace_then_replay(clocked_store: tuple[Store, list[float]]) -> None:
    store, now = clocked_store
    payload = _payload()

    assert store.use(payload) is Use.FIRST
    now[0] += REUSE_GRACE_SECONDS
    assert store.use(payload) is Use.WITHIN_GRACE
    now[0] += 1
    assert store.use(payload) is Use.REPLAYED


def test_a_replay_revokes_every_token_of_the_session(
    clocked_store: tuple[Store, list[float]],
) -> None:
    store, now = clocked_store
    old = _payload()
    sibling = _payload(session_id=old.session_id)
    store.use(old)
    now[0] += REUSE_GRACE_SECONDS + 1

    assert store.use(old) is Use.REPLAYED
    assert store.use(sibling) is Use.REVOKED


def test_revoke_affects_only_that_session(clocked_store: tuple[Store, list[float]]) -> None:
    store, _ = clocked_store
    mine, other = _payload(), _payload()

    store.revoke(mine.session_id)

    assert store.use(mine) is Use.REVOKED
    assert store.use(other) is Use.FIRST


def test_redis_keys_expire_with_the_token() -> None:
    client = MagicMock()
    client.pipeline.return_value.execute.return_value = [0, True, b"1"]
    payload = _payload()

    sessions.RedisSessionStore(client).use(payload)

    _, kwargs = client.pipeline.return_value.set.call_args
    days = get_settings().refresh_token_expire_days
    assert kwargs["nx"] is True
    assert 0 < kwargs["ex"] <= days * 86400 + 60


@pytest.mark.parametrize("operation", ["use", "revoke"])
def test_a_redis_outage_is_a_503_not_a_crash(operation: str) -> None:
    client = MagicMock()
    client.pipeline.side_effect = redis.ConnectionError("down")
    client.set.side_effect = redis.ConnectionError("down")
    store = sessions.RedisSessionStore(client)
    call: Callable[[], object] = (
        (lambda: store.use(_payload())) if operation == "use" else (lambda: store.revoke("s"))
    )

    with pytest.raises(sessions.SessionStoreUnavailableError):
        call()


def test_logout_survives_a_redis_outage() -> None:
    store = sessions.RedisSessionStore(MagicMock(set=MagicMock(side_effect=redis.RedisError)))
    token, _ = create_refresh_token(uuid.uuid4())

    sessions.end_session(store, token)  # does not raise
