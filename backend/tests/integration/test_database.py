import asyncio
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

pytestmark = pytest.mark.integration

BACKEND_DIR = Path(__file__).resolve().parents[2]


def _alembic_config(database_url: str) -> Config:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    return config


async def test_ready_returns_200_when_database_is_reachable(client: AsyncClient) -> None:
    response = await client.get("/api/v1/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready", "checks": {"database": "ok"}}


async def test_migrations_downgrade_and_upgrade_round_trip(test_database_url: str) -> None:
    config = _alembic_config(test_database_url)
    # Alembic's env.py runs its own event loop, so execute it off the test loop.
    await asyncio.to_thread(command.downgrade, config, "base")
    await asyncio.to_thread(command.upgrade, config, "head")

    engine = create_async_engine(test_database_url)
    try:
        async with engine.connect() as connection:
            result = await connection.execute(text("SELECT version_num FROM alembic_version"))
            version: str = result.scalar_one()
    finally:
        await engine.dispose()
    assert version == "0001_baseline"


async def test_session_factory_executes_queries(app: FastAPI) -> None:
    async with app.state.session_factory() as session:
        result = await session.execute(text("SELECT 1"))
        assert result.scalar_one() == 1
