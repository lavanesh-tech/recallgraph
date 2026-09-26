"""Authentication API against real PostgreSQL (users are SYNTHETIC test accounts)."""

import uuid
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import AsyncClient, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from recallgraph.auth.models import AuditEvent, RefreshToken
from recallgraph.auth.tokens import create_access_token

pytestmark = pytest.mark.integration

EMAIL = "alice@example.com"
PASSWORD = "correct horse battery staple 42"


@pytest.fixture
async def clean(session_factory: async_sessionmaker[AsyncSession]) -> None:
    return None


async def _register(client: AsyncClient, email: str = EMAIL) -> Response:
    return await client.post("/api/v1/auth/register", json={"email": email, "password": PASSWORD})


async def _login(client: AsyncClient, password: str = PASSWORD) -> dict[str, Any]:
    response = await client.post("/api/v1/auth/login", json={"email": EMAIL, "password": password})
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def test_register_returns_user_without_secrets(clean: None, client: AsyncClient) -> None:
    response = await _register(client, "  Alice@Example.COM ")

    assert response.status_code == 201
    body = response.json()
    assert set(body) == {"id", "email", "created_at"}
    assert body["email"] == EMAIL
    assert PASSWORD not in response.text


async def test_duplicate_email_is_conflict(clean: None, client: AsyncClient) -> None:
    await _register(client)
    response = await _register(client, EMAIL.upper())

    assert response.status_code == 409
    assert response.headers["content-type"].startswith("application/problem+json")


@pytest.mark.parametrize(
    "body",
    [
        {"email": EMAIL, "password": "Zq7!pw"},
        {"email": "not-an-email", "password": PASSWORD},
        {"email": EMAIL, "password": "p" * 129},
        {"email": EMAIL, "password": PASSWORD, "is_admin": True},
    ],
)
async def test_invalid_registration_is_rejected_without_echo(
    clean: None, client: AsyncClient, body: dict[str, object]
) -> None:
    response = await client.post("/api/v1/auth/register", json=body)

    assert response.status_code == 422
    assert str(body["password"]) not in response.text


async def test_login_then_me(clean: None, client: AsyncClient) -> None:
    await _register(client)
    tokens = await _login(client)

    assert tokens["token_type"] == "bearer"
    me = await client.get("/api/v1/auth/me", headers=_bearer(tokens["access_token"]))
    assert me.status_code == 200
    assert me.json()["email"] == EMAIL


async def test_login_failures_are_indistinguishable(clean: None, client: AsyncClient) -> None:
    await _register(client)
    wrong_password = await client.post(
        "/api/v1/auth/login", json={"email": EMAIL, "password": "wrong password 123"}
    )
    unknown_email = await client.post(
        "/api/v1/auth/login", json={"email": "nobody@example.com", "password": PASSWORD}
    )

    assert wrong_password.status_code == unknown_email.status_code == 401
    assert wrong_password.json()["detail"] == unknown_email.json()["detail"]


async def test_protected_route_rejects_bad_tokens(
    clean: None, client: AsyncClient, app: FastAPI
) -> None:
    user_id = (await _register(client)).json()["id"]
    tokens = await _login(client)
    expired, _ = create_access_token(uuid.UUID(user_id), app.state.settings, ttl_s=-5)

    missing = await client.get("/api/v1/auth/me")
    assert missing.status_code == 401
    assert missing.headers["www-authenticate"] == "Bearer"
    for bad in ("garbage", expired, tokens["refresh_token"]):
        response = await client.get("/api/v1/auth/me", headers=_bearer(bad))
        assert response.status_code == 401
        assert response.headers["content-type"].startswith("application/problem+json")


async def test_refresh_rotates_and_reuse_revokes_family(clean: None, client: AsyncClient) -> None:
    await _register(client)
    first = (await _login(client))["refresh_token"]

    rotated = await client.post("/api/v1/auth/refresh", json={"refresh_token": first})
    assert rotated.status_code == 200
    second = rotated.json()["refresh_token"]
    assert second != first

    reuse = await client.post("/api/v1/auth/refresh", json={"refresh_token": first})
    assert reuse.status_code == 401
    after_reuse = await client.post("/api/v1/auth/refresh", json={"refresh_token": second})
    assert after_reuse.status_code == 401  # whole family revoked on reuse


async def test_logout_revokes_session(clean: None, client: AsyncClient) -> None:
    await _register(client)
    refresh_token = (await _login(client))["refresh_token"]

    assert (
        await client.post("/api/v1/auth/logout", json={"refresh_token": refresh_token})
    ).status_code == 204
    again = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert again.status_code == 401


async def test_audit_trail_records_security_events_without_secrets(
    clean: None, client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    await _register(client)
    await client.post("/api/v1/auth/login", json={"email": EMAIL, "password": "bad password 1"})
    first = (await _login(client))["refresh_token"]
    await client.post("/api/v1/auth/refresh", json={"refresh_token": first})
    await client.post("/api/v1/auth/refresh", json={"refresh_token": first})

    async with session_factory() as session:
        events = (await session.execute(select(AuditEvent).order_by(AuditEvent.id))).scalars().all()
        stored = (await session.execute(select(RefreshToken.token_hash))).scalars().all()

    assert [e.event for e in events] == [
        "register",
        "login_failure",
        "login_success",
        "refresh",
        "refresh_reuse_detected",
    ]
    assert all(e.request_id for e in events)
    dumped = " ".join(str(e.details) for e in events)
    assert PASSWORD not in dumped and "bad password" not in dumped
    assert first not in stored  # only hashes are stored
