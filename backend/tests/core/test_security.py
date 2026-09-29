"""Unit tests for password hashing and JWT handling — no database needed."""

import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest
from argon2 import PasswordHasher

from app.core import security
from app.core.config import get_settings
from app.core.security import (
    JWT_ALGORITHM,
    JWT_AUDIENCE,
    JWT_ISSUER,
    TokenError,
    WeakPasswordError,
    create_access_token,
    decode_access_token,
    hash_password,
    password_needs_rehash,
    validate_password_strength,
    verify_password,
)

SECRET = get_settings().jwt_secret.get_secret_value()


def _claims(**overrides: object) -> dict[str, object]:
    now = datetime.now(UTC)
    claims: dict[str, object] = {
        "sub": str(uuid.uuid4()),
        "iss": JWT_ISSUER,
        "aud": JWT_AUDIENCE,
        "iat": now,
        "exp": now + timedelta(minutes=5),
        "jti": uuid.uuid4().hex,
        "typ": "access",
    }
    claims.update(overrides)
    return claims


def _encode(claims: dict[str, object], secret: str = SECRET, algorithm: str = JWT_ALGORITHM) -> str:
    return jwt.encode(claims, secret, algorithm=algorithm)


class TestPasswords:
    def test_hash_verifies_and_is_salted(self) -> None:
        first, second = (
            hash_password("a-long-enough-passphrase"),
            hash_password("a-long-enough-passphrase"),
        )
        assert first != second  # random salt
        assert verify_password("a-long-enough-passphrase", first)

    def test_wrong_password_is_rejected(self) -> None:
        assert not verify_password("wrong-password-here", hash_password("a-long-enough-passphrase"))

    def test_malformed_hash_is_rejected_not_raised(self) -> None:
        assert not verify_password("anything-at-all-1234", "not-an-argon2-hash")

    def test_hash_is_argon2id(self) -> None:
        assert hash_password("a-long-enough-passphrase").startswith("$argon2id$")

    def test_stronger_parameters_trigger_rehash(self, monkeypatch: pytest.MonkeyPatch) -> None:
        old_hash = hash_password("a-long-enough-passphrase")
        assert not password_needs_rehash(old_hash)
        monkeypatch.setattr(
            security, "_hasher", PasswordHasher(time_cost=2, memory_cost=16, parallelism=1)
        )
        assert password_needs_rehash(old_hash)

    @pytest.mark.parametrize("password", ["short", "elevenchars", ""])
    def test_short_passwords_rejected(self, password: str) -> None:
        with pytest.raises(WeakPasswordError):
            validate_password_strength(password)

    def test_overlong_password_rejected(self) -> None:
        with pytest.raises(WeakPasswordError):
            validate_password_strength("x" * 129)

    def test_acceptable_password_passes(self) -> None:
        validate_password_strength("twelve-chars")
        validate_password_strength("x" * 128)


class TestAccessTokens:
    def test_round_trip(self) -> None:
        user_id = uuid.uuid4()
        token, expires_at = create_access_token(user_id)
        payload = decode_access_token(token)
        assert payload.subject == user_id
        assert payload.expires_at == expires_at.replace(microsecond=0)
        assert payload.jti

    def test_each_token_has_a_unique_jti(self) -> None:
        user_id = uuid.uuid4()
        assert (
            decode_access_token(create_access_token(user_id)[0]).jti
            != decode_access_token(create_access_token(user_id)[0]).jti
        )

    def test_default_lifetime_comes_from_settings(self) -> None:
        now = datetime.now(UTC)
        _, expires_at = create_access_token(uuid.uuid4(), now=now)
        assert expires_at - now == timedelta(minutes=get_settings().access_token_expire_minutes)

    def test_expired_token_rejected(self) -> None:
        past = datetime.now(UTC) - timedelta(hours=2)
        token, _ = create_access_token(uuid.uuid4(), expires_delta=timedelta(minutes=5), now=past)
        with pytest.raises(TokenError):
            decode_access_token(token)

    def test_small_clock_skew_is_tolerated(self) -> None:
        just_expired = datetime.now(UTC) - timedelta(minutes=5, seconds=3)
        token, _ = create_access_token(
            uuid.uuid4(), expires_delta=timedelta(minutes=5), now=just_expired
        )
        decode_access_token(token)  # within the 10 s leeway

    def test_wrong_signature_rejected(self) -> None:
        with pytest.raises(TokenError):
            decode_access_token(_encode(_claims(), secret="x" * 64))

    def test_tampered_payload_rejected(self) -> None:
        token, _ = create_access_token(uuid.uuid4())
        header, _payload, signature = token.split(".")
        forged = _encode(_claims(sub=str(uuid.uuid4()))).split(".")[1]
        with pytest.raises(TokenError):
            decode_access_token(f"{header}.{forged}.{signature}")

    def test_alg_none_rejected(self) -> None:
        unsigned = jwt.encode(_claims(), key="", algorithm="none")
        with pytest.raises(TokenError):
            decode_access_token(unsigned)

    def test_other_hmac_algorithm_rejected(self) -> None:
        with pytest.raises(TokenError):
            decode_access_token(_encode(_claims(), secret=SECRET * 2, algorithm="HS512"))

    @pytest.mark.parametrize("claim", ["exp", "iat", "sub", "jti", "iss", "aud"])
    def test_missing_required_claim_rejected(self, claim: str) -> None:
        claims = _claims()
        del claims[claim]
        with pytest.raises(TokenError):
            decode_access_token(_encode(claims))

    def test_wrong_audience_rejected(self) -> None:
        with pytest.raises(TokenError):
            decode_access_token(_encode(_claims(aud="some-other-service")))

    def test_wrong_issuer_rejected(self) -> None:
        with pytest.raises(TokenError):
            decode_access_token(_encode(_claims(iss="someone-else")))

    def test_non_access_token_type_rejected(self) -> None:
        with pytest.raises(TokenError):
            decode_access_token(_encode(_claims(typ="refresh")))

    def test_non_uuid_subject_rejected(self) -> None:
        with pytest.raises(TokenError):
            decode_access_token(_encode(_claims(sub="not-a-uuid")))

    @pytest.mark.parametrize("garbage", ["", "abc", "a.b.c", "Bearer x"])
    def test_garbage_rejected(self, garbage: str) -> None:
        with pytest.raises(TokenError):
            decode_access_token(garbage)
