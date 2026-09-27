import os
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    DATABASE_URL: str = "sqlite:///./test.db"
    SECRET_KEY: str = "change-me-in-production"
    MAX_UPLOAD_SIZE_MB: int = 20  # Max file upload size in MB

    class Config:
        env_file = ".env"
        extra = "ignore"


@lru_cache
def get_settings() -> Settings:
    return Settings()
