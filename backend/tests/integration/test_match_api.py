"""Matching API against real PostgreSQL. All records are SYNTHETIC."""

from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from recallgraph.ingestion.runner import run_ingestion
from recallgraph.normalization.service import normalize_cpsc_records, normalize_source_records
from tests.integration.test_nhtsa_ingestion import _adapter
from tests.integration.test_normalization import _store
from tests.integration.test_search_api import HEATER
from tests.test_cpsc_normalizer import synthetic_payload
from tests.test_nhtsa_normalizer import synthetic_nhtsa

pytestmark = pytest.mark.integration


@pytest.fixture
async def catalog(session_factory: async_sessionmaker[AsyncSession]) -> None:
    await _store(session_factory, [synthetic_payload(RecallID=1), HEATER])
    await normalize_cpsc_records(session_factory)
    await run_ingestion(session_factory, _adapter([synthetic_nhtsa()]))
    await normalize_source_records(session_factory, "nhtsa")


async def _match(client: AsyncClient, **body: object) -> dict[str, Any]:
    response = await client.post("/api/v1/match", json=body)
    assert response.status_code == 200, response.text
    result: dict[str, Any] = response.json()
    return result


async def test_exact_model_returns_identifier_match(catalog: None, client: AsyncClient) -> None:
    body = await _match(client, model="AF-100X")

    top = body["matches"][0]
    assert (top["recall"]["source_record_id"], top["tier"], top["score"]) == (
        "1",
        "identifier_match",
        1.0,
    )
    assert body["engine_version"] == "match-2"


async def test_loose_description_is_explained(catalog: None, client: AsyncClient) -> None:
    body = await _match(client, description="black air fryer bought around 2024")

    assert [m["recall"]["source_record_id"] for m in body["matches"]] == ["1"]
    top = body["matches"][0]
    assert top["tier"] == "possible"
    names = {s["name"]: s for s in top["signals"]}
    assert names["lexical"]["applicable"] and names["date"]["applicable"]
    assert not names["identifier"]["applicable"]
    assert "air, fryer" in names["lexical"]["evidence"]


async def test_manufacturer_and_description_is_likely(catalog: None, client: AsyncClient) -> None:
    body = await _match(client, manufacturer="Acme", description="air fryer")

    assert body["matches"][0]["tier"] == "likely"


async def test_no_match_never_claims_safety(catalog: None, client: AsyncClient) -> None:
    body = await _match(client, description="zzqxv quantum toaster")

    assert body["matches"] == []
    assert "does not mean the product is safe" in body["disclaimer"]


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"category": "air fryer"},
        {"description": "x" * 501},
        {"upc": "12ab"},
        {"model": "AF-100X", "unexpected": 1},
        {"model": "AF-100X", "limit": 51},
    ],
)
async def test_invalid_match_requests_are_problems(
    client: AsyncClient, body: dict[str, object]
) -> None:
    response = await client.post("/api/v1/match", json=body)

    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/problem+json")
