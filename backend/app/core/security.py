"""Password hashing and JWT primitives (Role 5 — auth skeleton, US-19).

Design notes
------------
* **Argon2id** (via ``argon2-cffi``, RFC 9106 defaults) for passwords — the current OWASP
  recommendation. Hashes are self-describing, so parameters can be raised later and
  existing hashes are upgraded transparently on the next login (``password_needs_rehash``).
* **PyJWT** with a pinned algorithm (HS256). The algorithm is *not* configurable and the
  decoder only ever accepts that one, which closes the classic ``alg=none`` /
  algorithm-confusion attacks.
* Tokens are deliberately lean: ``sub`` (user id) plus standard claims. Role and workspace
  are looked up in the database on each request, so a demoted or deactivated user loses
  access immediately instead of when their token expires.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import lru_cache

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from app.core.config import get_settings

JWT_ALGORITHM = "HS256"
JWT_ISSUER = "ai-requirements-conflict-detector"
JWT_AUDIENCE = "rcd-api"
TOKEN_TYPE_ACCESS = "access"  # noqa: S105 — a claim value, not a credential
_CLOCK_SKEW_LEEWAY_SECONDS = 10

MIN_PASSWORD_LENGTH = 12
MAX_PASSWORD_LENGTH = 128


class TokenError(Exception):
    """The token is missing required claims, expired, tampered with, or otherwise invalid."""


class WeakPasswordError(ValueError):
    """The password does not satisfy the password policy."""


@dataclass(frozen=True)
class TokenPayload:
    subject: uuid.UUID
    jti: str
    issued_at: datetime
    expires_at: datetime


# ── Passwords ────────────────────────────────────────────────────────────────
_hasher = PasswordHasher()


def validate_password_strength(password: str) -> None:
    """Enforce the password policy (length-based, per NIST SP 800-63B guidance)."""
    if len(password) < MIN_PASSWORD_LENGTH:
        raise WeakPasswordError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters long")
    if len(password) > MAX_PASSWORD_LENGTH:
        raise WeakPasswordError(f"Password must be at most {MAX_PASSWORD_LENGTH} characters long")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def password_needs_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)


@lru_cache
def dummy_password_hash() -> str:
    """A valid hash of a throw-away value.

    Verifying against it when the email is unknown keeps login timing the same as for a real
    account, so response time can't be used to discover which emails are registered.
    """
    return _hasher.hash(uuid.uuid4().hex)


# ── JWT ──────────────────────────────────────────────────────────────────────
def create_access_token(
    subject: uuid.UUID,
    *,
    expires_delta: timedelta | None = None,
    now: datetime | None = None,
) -> tuple[str, datetime]:
    """Create a signed access token. Returns ``(token, expires_at)``."""
    settings = get_settings()
    issued_at = now or datetime.now(UTC)
    expires_at = issued_at + (
        expires_delta or timedelta(minutes=settings.access_token_expire_minutes)
    )
    claims = {
        "sub": str(subject),
        "iss": JWT_ISSUER,
        "aud": JWT_AUDIENCE,
        "iat": issued_at,
        "exp": expires_at,
        "jti": uuid.uuid4().hex,  # unique id — enables a revocation list later without a format change
        "typ": TOKEN_TYPE_ACCESS,
    }
    token = jwt.encode(claims, settings.jwt_secret.get_secret_value(), algorithm=JWT_ALGORITHM)
    return token, expires_at


def decode_access_token(token: str) -> TokenPayload:
    """Validate signature, expiry, issuer, audience and type. Raises :class:`TokenError`."""
    settings = get_settings()
    try:
        claims = jwt.decode(
            token,
            settings.jwt_secret.get_secret_value(),
            algorithms=[JWT_ALGORITHM],
            audience=JWT_AUDIENCE,
            issuer=JWT_ISSUER,
            leeway=_CLOCK_SKEW_LEEWAY_SECONDS,
            options={"require": ["exp", "iat", "sub", "jti", "iss", "aud"]},
        )
        if claims.get("typ") != TOKEN_TYPE_ACCESS:
            raise TokenError("Unexpected token type")
        return TokenPayload(
            subject=uuid.UUID(claims["sub"]),
            jti=str(claims["jti"]),
            issued_at=datetime.fromtimestamp(claims["iat"], tz=UTC),
            expires_at=datetime.fromtimestamp(claims["exp"], tz=UTC),
        )
    except (jwt.PyJWTError, ValueError, KeyError) as exc:
        raise TokenError("Invalid or expired token") from exc
