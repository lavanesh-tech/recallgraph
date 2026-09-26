"""Recall Radar against real PostgreSQL (SYNTHETIC users, items and recalls)."""

from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from recallgraph.normalization.service import normalize_cpsc_records
from recallgraph.radar.models import RadarAlert, RadarRun
from recallgraph.radar.service import RADAR_LOCK_KEY, run_radar
from tests.integration.test_normalization import _store
from tests.test_cpsc_normalizer import synthetic_payload

pytestmark = pytest.mark.integration

PASSWORD = "correct horse battery staple 42"
TOASTER = synthetic_payload(
    RecallID=5,
    Title="SYNTHETIC Zeta Recalls Toasters Due to Fire Hazard",
    Description="Zeta toasters can overheat.",
    Products=[{"Name": "Zeta Toaster", "Model": "ZX-9000", "Type": "Toasters"}],
    Manufacturers=[{"Name": "Zeta Home LLC, of Dayton, Ohio"}],
    Importers=[],
    ProductUPCs=[],
)


@pytest.fixture
async def catalog(session_factory: async_sessionmaker[AsyncSession]) -> None:
    await _store(session_factory, [synthetic_payload(RecallID=1)])
    await normalize_cpsc_records(session_factory)


async def _auth(client: AsyncClient, email: str) -> dict[str, str]:
    await client.post("/api/v1/auth/register", json={"email": email, "password": PASSWORD})
    response = await client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def _item(client: AsyncClient, headers: dict[str, str], body: dict[str, object]) -> None:
    response = await client.post("/api/v1/inventory", json=body, headers=headers)
    assert response.status_code == 201, response.text


async def _alerts(client: AsyncClient, headers: dict[str, str], **params: str) -> dict[str, Any]:
    response = await client.get("/api/v1/radar/alerts", headers=headers, params=params)
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


async def _alert_count(factory: async_sessionmaker[AsyncSession]) -> int:
    async with factory() as session:
        count: int = (
            await session.execute(select(func.count()).select_from(RadarAlert))
        ).scalar_one()
    return count


async def test_radar_alerts_new_recalls_and_existing_matches_idempotently(
    catalog: None, client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    alice = await _auth(client, "alice@example.com")
    bob = await _auth(client, "bob@example.com")
    await _item(client, alice, {"nickname": "Air fryer", "model": "AF-100X"})
    await _item(client, alice, {"nickname": "Old fryer", "description": "black air fryer"})
    await _item(client, bob, {"nickname": "Toaster", "model": "ZX-9000"})

    first = await run_radar(session_factory)
    assert (first.status, first.alerts_created) == ("succeeded", 1)  # alice's exact model only

    await _store(session_factory, [TOASTER])  # a new official recall arrives
    await normalize_cpsc_records(session_factory)
    second = await run_radar(session_factory)
    third = await run_radar(session_factory)

    assert second.alerts_created == 1  # bob's toaster, found by the reverse scan
    assert third.alerts_created == 0  # re-scans never duplicate alerts
    assert await _alert_count(session_factory) == 2

    alice_alerts = await _alerts(client, alice)
    assert [a["recall"]["source_record_id"] for a in alice_alerts["items"]] == ["1"]
    assert alice_alerts["items"][0]["tier"] == "identifier_match"
    assert alice_alerts["items"][0]["item"]["nickname"] == "Air fryer"
    bob_alerts = await _alerts(client, bob)
    assert [a["recall"]["source_record_id"] for a in bob_alerts["items"]] == ["5"]


async def test_alerts_are_private_and_can_be_marked_read(
    catalog: None, client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    alice = await _auth(client, "alice@example.com")
    bob = await _auth(client, "bob@example.com")
    await _item(client, alice, {"nickname": "Air fryer", "model": "AF-100X"})
    await run_radar(session_factory)
    alert_id = (await _alerts(client, alice))["items"][0]["id"]

    assert (await _alerts(client, bob))["total"] == 0
    stolen = await client.post(f"/api/v1/radar/alerts/{alert_id}/read", headers=bob)
    assert stolen.status_code == 404

    assert (await _alerts(client, alice))["unread"] == 1
    read = await client.post(f"/api/v1/radar/alerts/{alert_id}/read", headers=alice)
    assert read.status_code == 204
    assert (await _alerts(client, alice))["unread"] == 0
    assert (await _alerts(client, alice, unread_only="true"))["total"] == 0


async def test_read_all_marks_only_own_alerts(
    catalog: None, client: AsyncClient, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    alice = await _auth(client, "alice@example.com")
    await _item(client, alice, {"nickname": "Air fryer", "model": "AF-100X"})
    await run_radar(session_factory)

    response = await client.post("/api/v1/radar/alerts/read-all", headers=alice)

    assert response.json() == {"marked": 1}
    assert (await client.get("/api/v1/radar/alerts")).status_code == 401


async def test_concurrent_run_is_skipped_by_advisory_lock(
    catalog: None, session_factory: async_sessionmaker[AsyncSession], test_database_url: str
) -> None:
    engine = create_async_engine(test_database_url)
    try:
        async with engine.connect() as holder:
            await holder.execute(text("SELECT pg_advisory_lock(:k)"), {"k": RADAR_LOCK_KEY})
            summary = await run_radar(session_factory)
            await holder.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": RADAR_LOCK_KEY})
    finally:
        await engine.dispose()

    assert summary.status == "skipped"
    async with session_factory() as session:
        runs = (await session.execute(select(func.count()).select_from(RadarRun))).scalar_one()
    assert runs == 0
