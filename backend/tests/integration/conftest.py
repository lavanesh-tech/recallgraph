from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

BACKEND_DIR = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="session")
def alembic_config(test_database_url: str) -> Config:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", test_database_url.replace("%", "%%"))
    return config


@pytest.fixture(scope="session")
def migrated_database(alembic_config: Config, test_database_url: str) -> str:
    command.upgrade(alembic_config, "head")
    return test_database_url


@pytest.fixture
async def db_session(migrated_database: str) -> AsyncIterator[AsyncSession]:
    """A session on a freshly emptied schema; each test starts from a known state."""
    engine = create_async_engine(migrated_database)
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "TRUNCATE radar_runs, users, audit_events, companies, "
                "raw_records, ingestion_runs, sources "
                "RESTART IDENTITY CASCADE"
            )
        )
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            yield session
    finally:
        await engine.dispose()


@pytest.fixture
async def session_factory(
    migrated_database: str,
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """A session factory on a freshly emptied schema (for code that manages its own sessions)."""
    engine = create_async_engine(migrated_database)
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "TRUNCATE radar_runs, users, audit_events, companies, "
                "raw_records, ingestion_runs, sources "
                "RESTART IDENTITY CASCADE"
            )
        )
    try:
        yield async_sessionmaker(engine, expire_on_commit=False)
    finally:
        await engine.dispose()
