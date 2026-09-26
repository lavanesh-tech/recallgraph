import asyncio

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

pytestmark = pytest.mark.integration


async def test_ready_returns_200_when_database_is_reachable(client: AsyncClient) -> None:
    response = await client.get("/api/v1/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready", "checks": {"database": "ok"}}


async def test_migrations_downgrade_and_upgrade_round_trip(
    alembic_config: Config, test_database_url: str
) -> None:
    # Alembic's env.py runs its own event loop, so execute it off the test loop.
    await asyncio.to_thread(command.downgrade, alembic_config, "base")
    await asyncio.to_thread(command.upgrade, alembic_config, "head")

    engine = create_async_engine(test_database_url)
    try:
        async with engine.connect() as connection:
            result = await connection.execute(text("SELECT version_num FROM alembic_version"))
            current: str = result.scalar_one()
    finally:
        await engine.dispose()
    assert current == ScriptDirectory.from_config(alembic_config).get_current_head()


async def test_session_factory_executes_queries(app: FastAPI) -> None:
    async with app.state.session_factory() as session:
        result = await session.execute(text("SELECT 1"))
        assert result.scalar_one() == 1
