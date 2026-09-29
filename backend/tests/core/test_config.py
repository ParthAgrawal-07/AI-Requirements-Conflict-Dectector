"""Unit tests for settings validation — no database needed."""

import pytest
from pydantic import ValidationError

from app.core.config import Environment, Settings

GOOD_SECRET = "a-genuinely-random-secret-with-plenty-of-length-0123456789"
BASE = {
    "database_url": "postgresql://u:p@db:5432/app",
    "redis_url": "redis://redis:6379/0",
    "jwt_secret": GOOD_SECRET,
}


def make(**overrides: object) -> Settings:
    return Settings(_env_file=None, **{**BASE, **overrides})  # type: ignore[arg-type]


def test_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ENVIRONMENT", raising=False)  # the test session itself runs as "test"
    settings = make()
    assert settings.environment is Environment.DEVELOPMENT
    assert settings.access_token_expire_minutes == 60
    assert settings.max_upload_size_bytes == 25 * 1024 * 1024
    assert settings.similarity_threshold_default == 0.75
    assert settings.cors_allowed_origins == ["http://localhost:5173"]
    assert not settings.use_json_logs


@pytest.mark.parametrize(
    ("given", "expected_prefix"),
    [
        ("postgres://u:p@h/db", "postgresql+psycopg2://u:p@h/db"),
        ("postgresql://u:p@h/db", "postgresql+psycopg2://u:p@h/db"),
        ("postgresql+psycopg2://u:p@h/db", "postgresql+psycopg2://u:p@h/db"),
    ],
)
def test_database_url_is_normalised(given: str, expected_prefix: str) -> None:
    assert make(database_url=given).database_url == expected_prefix


def test_non_postgres_database_url_rejected() -> None:
    with pytest.raises(ValidationError):
        make(database_url="mysql://u:p@h/db")


def test_cors_origins_parsed_from_comma_separated_string() -> None:
    settings = make(cors_allowed_origins="http://a.test, https://b.test ,,")
    assert settings.cors_allowed_origins == ["http://a.test", "https://b.test"]


def test_cors_origins_read_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "http://a.test,http://b.test")
    assert Settings(_env_file=None).cors_allowed_origins == ["http://a.test", "http://b.test"]  # type: ignore[call-arg]


@pytest.mark.parametrize("name", ["SIMILARITY_THRESHOLD", "SIMILARITY_THRESHOLD_DEFAULT"])
def test_similarity_threshold_accepts_both_env_names(
    monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    monkeypatch.setenv(name, "0.6")
    assert Settings(_env_file=None).similarity_threshold_default == 0.6  # type: ignore[call-arg]


def test_similarity_threshold_must_be_a_probability() -> None:
    with pytest.raises(ValidationError):
        make(similarity_threshold_default=1.5)


@pytest.mark.parametrize("environment", ["staging", "production"])
class TestProductionSafety:
    def test_short_secret_rejected(self, environment: str) -> None:
        with pytest.raises(ValidationError, match="JWT_SECRET"):
            make(environment=environment, jwt_secret="too-short")

    def test_dev_placeholder_secret_rejected(self, environment: str) -> None:
        with pytest.raises(ValidationError, match="JWT_SECRET"):
            make(environment=environment, jwt_secret="dev-only-" + "x" * 60)

    def test_wildcard_cors_rejected(self, environment: str) -> None:
        with pytest.raises(ValidationError, match="CORS"):
            make(environment=environment, cors_allowed_origins="*")

    def test_strong_config_accepted_and_uses_json_logs(self, environment: str) -> None:
        settings = make(environment=environment)
        assert settings.use_json_logs


def test_weak_secret_is_fine_in_development_and_test() -> None:
    make(environment="development", jwt_secret="dev-only-short")
    make(environment="test", jwt_secret="whatever")


def test_secret_is_not_leaked_by_repr() -> None:
    assert GOOD_SECRET not in repr(make())
