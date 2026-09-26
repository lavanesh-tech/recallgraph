"""Security middleware behaviour through the real app."""

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from recallgraph.core.config import Settings

pytestmark = pytest.mark.integration


def _tune(app: FastAPI, **changes: object) -> None:
    settings: Settings = app.state.settings
    app.state.settings = settings.model_copy(update=changes)


async def test_security_headers_on_api_and_error_responses(client: AsyncClient) -> None:
    for response in (
        await client.get("/api/v1/health"),
        await client.get("/api/v1/recalls/999999999"),
    ):
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["x-frame-options"] == "DENY"
        assert response.headers["referrer-policy"] == "no-referrer"
        assert "default-src 'none'" in response.headers["content-security-policy"]
        assert "strict-transport-security" not in response.headers  # local environment


async def test_auth_responses_are_not_cached(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/auth/login", json={"email": "x@example.com", "password": "p"}
    )
    assert response.headers["cache-control"] == "no-store"


async def test_login_is_rate_limited_per_client(client: AsyncClient, app: FastAPI) -> None:
    _tune(app, auth_rate_limit_per_minute=3)
    body = {"email": "nobody@example.com", "password": "wrong password 123"}
    statuses = [(await client.post("/api/v1/auth/login", json=body)).status_code for _ in range(4)]

    assert 429 not in statuses[:3]
    assert statuses[3] == 429
    limited = await client.post("/api/v1/auth/login", json=body)
    assert limited.headers["content-type"] == "application/problem+json"
    assert int(limited.headers["retry-after"]) >= 1
    assert limited.headers["x-request-id"]
    # Other endpoints are unaffected.
    assert (await client.get("/api/v1/health")).status_code == 200


async def test_oversized_bodies_are_rejected(client: AsyncClient, app: FastAPI) -> None:
    _tune(app, max_body_bytes=1_024)
    response = await client.post("/api/v1/match", json={"description": "x" * 5_000})

    assert response.status_code == 413
    assert response.json()["status"] == 413


async def test_cors_is_closed_by_default(client: AsyncClient) -> None:
    response = await client.get("/api/v1/health", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in response.headers


def test_docs_disabled_in_production() -> None:
    from recallgraph.main import create_app

    settings = Settings(environment="production", jwt_secret="x" * 64)  # noqa: S106
    app = create_app(settings)
    assert app.docs_url is None and app.openapi_url is None
