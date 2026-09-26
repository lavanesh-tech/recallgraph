"""Centralized, environment-driven application settings."""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["local", "test", "staging", "production"]
LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR"]


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


@lru_cache
def get_settings() -> Settings:
    return Settings()
