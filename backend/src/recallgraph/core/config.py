"""Centralized, environment-driven application settings."""

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["local", "test", "staging", "production"]
LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR"]

# Local-development default only (Docker Compose on 127.0.0.1:5433). Deployed environments
# must supply RECALLGRAPH_DATABASE_URL from a secret store.
_LOCAL_DATABASE_URL = "postgresql+asyncpg://recallgraph:recallgraph@127.0.0.1:5433/recallgraph"


class Settings(BaseSettings):
    """Runtime configuration from RECALLGRAPH_* environment variables or a local .env."""

    model_config = SettingsConfigDict(
        env_prefix="RECALLGRAPH_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "RecallGraph"
    environment: Environment = "local"
    log_level: LogLevel = "INFO"
    log_json: bool = True

    database_url: str = _LOCAL_DATABASE_URL
    db_pool_size: int = Field(default=5, ge=1, le=50)
    db_max_overflow: int = Field(default=5, ge=0, le=50)
    db_readiness_timeout_s: float = Field(default=2.0, gt=0, le=30)


@lru_cache
def get_settings() -> Settings:
    return Settings()
