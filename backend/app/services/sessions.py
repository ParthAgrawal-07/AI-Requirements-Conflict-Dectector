"""Refresh sessions — silent re-login (Parth — US-19, NFR-11).

Sign-in returns a short-lived access token in the body (kept in memory by the SPA) and a
refresh token in an HttpOnly cookie. ``POST /auth/refresh`` trades the cookie for a new access
token and a **new** refresh token (rotation):

* each refresh token is single-use. Its ``jti`` is recorded in Redis on first use;
* a token used again after :data:`REUSE_GRACE_SECONDS` means two parties hold it — a stolen
  cookie, or the real user after the thief — so the whole session is revoked;
* inside the grace window a second use is answered normally. Two tabs share one cookie, and
  when they refresh at the same moment one of them presents the token the other just rotated;
* logout revokes the session, so its outstanding tokens stop working at once;
* the user is re-read on every refresh: a deactivated account cannot refresh.

State lives in Redis with TTLs (no table, no migration): ``auth:refresh:used:<jti>`` holds the
time of first use, ``auth:session:revoked:<sid>`` marks a revoked session. If Redis is
unreachable, refresh **fails closed** (503) and the SPA sends the user to sign in — exactly what
happened before refresh existed. Tokens are signed JWTs, so Redis never holds a credential.
"""

import logging
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from functools import lru_cache
from typing import Protocol

import redis
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import ServiceUnavailableError, SessionExpiredError
from app.core.security import (
    RefreshPayload,
    TokenError,
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
)
from app.models import User
from app.services.users import get_user

logger = logging.getLogger(__name__)

REUSE_GRACE_SECONDS = 30
USED_PREFIX = "auth:refresh:used:"
REVOKED_PREFIX = "auth:session:revoked:"


class Use(StrEnum):
    FIRST = "first"
    WITHIN_GRACE = "within_grace"
    REPLAYED = "replayed"
    REVOKED = "revoked"


class SessionStoreUnavailableError(ServiceUnavailableError):
    def __init__(self) -> None:
        super().__init__(
            "Sessions are temporarily unavailable. Please sign in again.",
            code="session_store_unavailable",
        )


class SessionStore(Protocol):
    def use(self, payload: RefreshPayload) -> Use:
        """Record one use of a refresh token and say what kind of use it was."""
        ...

    def revoke(self, session_id: str) -> None: ...


def _ttl_seconds(expires_at: datetime) -> int:
    return max(1, int((expires_at - datetime.now(UTC)).total_seconds()) + 60)


def _session_ttl_seconds() -> int:
    # A revoked marker must outlive every token of the session; none lives longer than this.
    return get_settings().refresh_token_expire_days * 24 * 60 * 60 + 60


class RedisSessionStore:
    def __init__(self, client: redis.Redis, clock: Callable[[], float] = time.time) -> None:
        self._client = client
        self._clock = clock

    def use(self, payload: RefreshPayload) -> Use:
        now = int(self._clock())
        used_key = f"{USED_PREFIX}{payload.jti}"
        try:
            pipe = self._client.pipeline()
            pipe.exists(f"{REVOKED_PREFIX}{payload.session_id}")
            pipe.set(used_key, now, nx=True, ex=_ttl_seconds(payload.expires_at))
            pipe.get(used_key)
            revoked, first, used_at = pipe.execute()
        except redis.RedisError:
            raise SessionStoreUnavailableError() from None
        if revoked:
            return Use.REVOKED
        if first:
            return Use.FIRST
        if used_at is not None and now - int(used_at) <= REUSE_GRACE_SECONDS:
            return Use.WITHIN_GRACE
        self.revoke(payload.session_id)
        return Use.REPLAYED

    def revoke(self, session_id: str) -> None:
        try:
            self._client.set(f"{REVOKED_PREFIX}{session_id}", 1, ex=_session_ttl_seconds())
        except redis.RedisError:
            raise SessionStoreUnavailableError() from None


class InMemorySessionStore:
    """Process-local store for tests. Same semantics, no expiry (tests are short)."""

    def __init__(self, clock: Callable[[], float] = time.time) -> None:
        self._clock = clock
        self._used: dict[str, float] = {}
        self._revoked: set[str] = set()
        self._lock = threading.Lock()

    def use(self, payload: RefreshPayload) -> Use:
        now = self._clock()
        with self._lock:
            if payload.session_id in self._revoked:
                return Use.REVOKED
            used_at = self._used.get(payload.jti)
            if used_at is None:
                self._used[payload.jti] = now
                return Use.FIRST
            if now - used_at <= REUSE_GRACE_SECONDS:
                return Use.WITHIN_GRACE
            self._revoked.add(payload.session_id)
            return Use.REPLAYED

    def revoke(self, session_id: str) -> None:
        with self._lock:
            self._revoked.add(session_id)


@lru_cache
def get_session_store() -> SessionStore:
    """FastAPI dependency: the Redis-backed store. Tests override it."""
    client = redis.Redis.from_url(
        get_settings().redis_url, socket_connect_timeout=2, socket_timeout=2
    )
    return RedisSessionStore(client)


@dataclass(frozen=True)
class IssuedTokens:
    access_token: str
    access_expires_at: datetime
    refresh_token: str
    refresh_expires_at: datetime


def start_session(user_id: uuid.UUID) -> IssuedTokens:
    """Tokens for a fresh sign-in (login or sign-up)."""
    return _issue(user_id, session_id=None)


def _issue(user_id: uuid.UUID, *, session_id: str | None) -> IssuedTokens:
    access, access_expires_at = create_access_token(user_id)
    refresh, payload = create_refresh_token(user_id, session_id=session_id)
    return IssuedTokens(access, access_expires_at, refresh, payload.expires_at)


def refresh_session(db: Session, store: SessionStore, refresh_token: str | None) -> IssuedTokens:
    """Rotate ``refresh_token``. Raises :class:`SessionExpiredError` if it cannot be used."""
    if not refresh_token:
        raise SessionExpiredError()
    try:
        payload = decode_refresh_token(refresh_token)
    except TokenError:
        raise SessionExpiredError() from None

    use = store.use(payload)
    if use is Use.REPLAYED:
        logger.warning(
            "Refresh token replayed; session %s revoked (user %s)",
            payload.session_id,
            payload.subject,
        )
    if use in (Use.REPLAYED, Use.REVOKED):
        raise SessionExpiredError()

    user: User | None = get_user(db, payload.subject)
    if user is None or not user.is_active:
        store.revoke(payload.session_id)
        raise SessionExpiredError()
    return _issue(user.id, session_id=payload.session_id)


def end_session(store: SessionStore, refresh_token: str | None) -> None:
    """Revoke the cookie's session. Best effort: logout always succeeds for the user."""
    if not refresh_token:
        return
    try:
        payload = decode_refresh_token(refresh_token)
    except TokenError:
        return  # expired or forged: nothing left to revoke
    try:
        store.revoke(payload.session_id)
    except SessionStoreUnavailableError:
        logger.warning("Could not revoke session %s: Redis unavailable", payload.session_id)
