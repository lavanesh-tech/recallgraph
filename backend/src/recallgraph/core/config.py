"""Centralized, environment-driven application settings."""

from functools import lru_cache
from typing import Literal, Self

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Environment = Literal["local", "test", "staging", "production"]
LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR"]

# Local-development default only (Docker Compose on 127.0.0.1:5433). Deployed environments
# must supply RECALLGRAPH_DATABASE_URL from a secret store.
_LOCAL_DATABASE_URL = "postgresql+asyncpg://recallgraph:recallgraph@127.0.0.1:5433/recallgraph"
# Local/test only. Deployed environments are refused unless a real secret is supplied.
DEV_JWT_SECRET = "dev-only-insecure-jwt-secret-do-not-deploy-0000"  # noqa: S105 - refused outside local/test
MIN_JWT_SECRET_LENGTH = 32


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

    jwt_secret: SecretStr = SecretStr(DEV_JWT_SECRET)
    jwt_issuer: str = "recallgraph"
    jwt_audience: str = "recallgraph-api"
    access_token_ttl_s: int = Field(default=900, ge=60, le=3600)
    refresh_token_ttl_s: int = Field(default=1_209_600, ge=3600, le=7_776_000)

    # Local Mailpit (docker compose) by default; a real SMTP relay when deployed.
    smtp_host: str = "127.0.0.1"
    smtp_port: int = Field(default=1026, ge=1, le=65535)
    mail_from: str = "RecallGraph Radar <radar@recallgraph.local>"

    # Optional. Without a key, explanations use the deterministic evidence template.
    openai_api_key: SecretStr | None = None
    openai_model: str = "gpt-4o-mini"
    openai_timeout_s: float = Field(default=20.0, gt=0, le=120)

    @model_validator(mode="after")
    def _require_real_secret_when_deployed(self) -> Self:
        if self.environment in ("staging", "production"):
            secret = self.jwt_secret.get_secret_value()
            if secret == DEV_JWT_SECRET or len(secret) < MIN_JWT_SECRET_LENGTH:
                raise ValueError(
                    "RECALLGRAPH_JWT_SECRET must be a random value of at least "
                    f"{MIN_JWT_SECRET_LENGTH} characters outside local/test"
                )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
