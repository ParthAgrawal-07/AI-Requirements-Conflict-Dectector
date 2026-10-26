"""Application settings (Role 5 — Backend API & Orchestration).

Single source of truth for configuration. Every value comes from environment variables
(12-factor); a local ``.env`` file is read as a convenience. Invalid or missing required
values fail fast at startup instead of surfacing as confusing errors later.

Usage::

    from app.core.config import get_settings

    settings = get_settings()
"""

from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import AliasChoices, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

MIN_PRODUCTION_SECRET_LENGTH = 32
DEV_SECRET_PREFIX = "dev-only"  # noqa: S105 — a placeholder marker, not a credential


Effort = Literal["low", "medium", "high", "xhigh", "max"]  # LLM effort levels (Keval)


class Environment(StrEnum):
    DEVELOPMENT = "development"
    TEST = "test"
    STAGING = "staging"
    PRODUCTION = "production"


class Settings(BaseSettings):
    """Typed, validated application configuration."""

    model_config = SettingsConfigDict(
        # Works from backend/ (local dev) and from the repo root; real env vars always win.
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",  # .env also carries POSTGRES_*, VITE_* etc. for other services
        case_sensitive=False,
        populate_by_name=True,
    )

    # ── Runtime ───────────────────────────────────────────
    environment: Environment = Environment.DEVELOPMENT
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"

    # ── Infrastructure ────────────────────────────────────
    database_url: str
    redis_url: str

    # ── Auth (FR-37, NFR-11, NFR-12) ──────────────────────
    jwt_secret: SecretStr
    access_token_expire_minutes: int = Field(default=60, ge=1, le=24 * 60)
    # FR-43: who may create workspaces. False = platform admins only (the CLI creates the first
    # one); True = any signed-in user. Sign-up itself always needs a join code (SX-02).
    allow_user_workspace_creation: bool = False
    # NFR-35: join-code attempts are limited per IP and per e-mail address on sign-up.
    signup_attempts_per_minute: int = Field(default=5, ge=1, le=1000)
    # How many reverse proxies sit in front of the API (Render, nginx...). Needed so rate limits
    # key on the real client address: with 0 the socket peer is used and X-Forwarded-For is
    # ignored (it can be forged); with N, the N-th entry from the right is trusted.
    trusted_proxy_hops: int = Field(default=0, ge=0, le=5)

    # ── HTTP ──────────────────────────────────────────────
    cors_allowed_origins: Annotated[list[str], NoDecode] = ["http://localhost:5173"]

    # ── Uploads (FR-02, used from Sprint 1) ───────────────
    max_upload_size_mb: int = Field(default=25, ge=1, le=500)
    upload_dir: Path = Path("./uploads")

    # ── Pipeline defaults (FR-10, owned by Roles 2/3) ─────
    similarity_threshold_default: float = Field(
        default=0.75,
        ge=0.0,
        le=1.0,
        # .env.example historically used SIMILARITY_THRESHOLD; docs use *_DEFAULT. Accept both.
        validation_alias=AliasChoices("SIMILARITY_THRESHOLD_DEFAULT", "SIMILARITY_THRESHOLD"),
    )
    llm_provider: Literal["gemini", "groq", "anthropic", "openai"] = "gemini"
    llm_fallback_provider: Literal["groq", "none"] | None = "groq"
    gemini_api_key: SecretStr | None = None
    gemini_model: str = "gemini-2.5-flash"
    groq_api_key: SecretStr | None = None
    groq_model: str = "llama-3.3-70b-versatile"
    llm_api_key: SecretStr | None = None
    llm_model: str = "gemini-2.5-flash"
    llm_effort: Effort = "low"
    llm_timeout_seconds: float = Field(default=60.0, gt=0, le=600)
    llm_max_retries: int = Field(default=2, ge=0, le=6)  # transport retries (429, 5xx, network)

    # ── Validators ────────────────────────────────────────
    @field_validator("database_url")
    @classmethod
    def _normalize_database_url(cls, value: str) -> str:
        # Heroku/Render/Railway historically hand out "postgres://"; SQLAlchemy 2 rejects it.
        if value.startswith("postgres://"):
            value = "postgresql://" + value.removeprefix("postgres://")
        # A bare "postgresql://" means psycopg2 on SQLAlchemy 2.0 but psycopg (v3) on 2.1+.
        # Pin the driver we ship (psycopg2-binary) so behaviour never depends on the version.
        if value.startswith("postgresql://"):
            value = "postgresql+psycopg2://" + value.removeprefix("postgresql://")
        if not value.startswith("postgresql"):
            raise ValueError("DATABASE_URL must be a PostgreSQL URL (postgresql://...)")
        return value

    @field_validator("cors_allowed_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @model_validator(mode="after")
    def _enforce_production_safety(self) -> Self:
        if self.environment in (Environment.STAGING, Environment.PRODUCTION):
            secret = self.jwt_secret.get_secret_value()
            if len(secret) < MIN_PRODUCTION_SECRET_LENGTH or secret.startswith(DEV_SECRET_PREFIX):
                raise ValueError(
                    "JWT_SECRET is too weak for staging/production: use at least "
                    f"{MIN_PRODUCTION_SECRET_LENGTH} random characters — generate one with "
                    '`python -c "import secrets; print(secrets.token_urlsafe(48))"`'
                )
            if "*" in self.cors_allowed_origins:
                raise ValueError("CORS_ALLOWED_ORIGINS must list explicit origins, not '*'")
        return self

    # ── Derived helpers ───────────────────────────────────
    @property
    def is_production(self) -> bool:
        return self.environment is Environment.PRODUCTION

    @property
    def use_json_logs(self) -> bool:
        return self.environment in (Environment.STAGING, Environment.PRODUCTION)

    @property
    def max_upload_size_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    """Return the cached settings instance (call ``get_settings.cache_clear()`` in tests)."""
    return Settings()  # type: ignore[call-arg]  # required fields come from the environment
