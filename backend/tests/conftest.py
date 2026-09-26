import os
from collections.abc import AsyncIterator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from recallgraph.core.config import Settings
from recallgraph.main import create_app

_DEFAULT_TEST_DATABASE_URL = (
    "postgresql+asyncpg://recallgraph:recallgraph@127.0.0.1:5433/recallgraph_test"
)


@pytest.fixture(scope="session")
def test_database_url() -> str:
    # Integration tests use a dedicated database, never the development one.
    return os.environ.get("TEST_DATABASE_URL", _DEFAULT_TEST_DATABASE_URL)


@pytest.fixture
def settings(test_database_url: str) -> Settings:
    return Settings(
        environment="test", log_level="WARNING", log_json=True, database_url=test_database_url
    )


@pytest.fixture
async def app(settings: Settings) -> AsyncIterator[FastAPI]:
    application = create_app(settings)
    yield application
    await application.state.engine.dispose()


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    # raise_app_exceptions=False lets tests assert on the real 500 response.
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://testserver") as http:
        yield http
