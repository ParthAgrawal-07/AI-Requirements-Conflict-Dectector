from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    DATABASE_URL: str = "sqlite:///./test.db"
    SECRET_KEY: str = "change-me-in-production"
    MAX_UPLOAD_SIZE_MB: int = 20  # Max file upload size in MB


@lru_cache
def get_settings() -> Settings:
    return Settings()
