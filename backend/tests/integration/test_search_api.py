"""Search and detail API against real PostgreSQL. All records are SYNTHETIC."""

from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from recallgraph.ingestion.runner import run_ingestion
from recallgraph.normalization.service import normalize_cpsc_records, normalize_source_records
from tests.integration.test_nhtsa_ingestion import _adapter
from tests.integration.test_normalization import _store
from tests.test_cpsc_normalizer import synthetic_payload
from tests.test_nhtsa_normalizer import synthetic_nhtsa

pytestmark = pytest.mark.integration

HEATER = synthetic_payload(
    RecallID=2,
    Title="SYNTHETIC Beta Recalls Space Heaters Due to Burn Hazard",
    Description="Beta space heaters can overheat.",
    RecallDate="2019-03-01T00:00:00",
    Products=[{"Name": "Beta Space Heaters", "Model": "BH-7Z", "Type": "Heaters"}],
    Manufacturers=[{"Name": "Beta Heat Inc., of Dayton, Ohio"}],
    Importers=[],
    ProductUPCs=[],
)


@pytest.fixture
async def seeded(session_factory: async_sessionmaker[AsyncSession]) -> None:
    await _store(session_factory, [synthetic_payload(RecallID=1), HEATER])
    await normalize_cpsc_records(session_factory)
    await run_ingestion(session_factory, _adapter([synthetic_nhtsa()]))
    await normalize_source_records(session_factory, "nhtsa")


async def _search(client: AsyncClient, **params: str | int) -> dict[str, Any]:
    response = await client.get("/api/v1/recalls", params=params)
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def _ids(body: dict[str, Any]) -> list[str]:
    return [item["source_record_id"] for item in body["items"]]


async def test_full_text_search_returns_ranked_hit_with_companies(
    seeded: None, client: AsyncClient
) -> None:
    body = await _search(client, q="air fryer")

    assert body["total"] == 1
    hit = body["items"][0]
    assert (hit["source"], hit["source_record_id"]) == ("cpsc", "1")
    assert hit["score"] > 0
    assert {"role": "manufacturer", "name": "Acme Manufacturing Co., Ltd."} in hit["companies"]


async def test_trigram_matching_tolerates_typos(seeded: None, client: AsyncClient) -> None:
    assert _ids(await _search(client, q="acme recalls air fryrs")) == ["1"]


@pytest.mark.parametrize(
    ("params", "expected"),
    [
        ({"source": "nhtsa"}, ["99V000001"]),
        ({"manufacturer": "beta heat"}, ["2"]),
        ({"model": "bh 7z"}, ["2"]),
        ({"model": "AF-100X"}, ["1"]),
        ({"date_from": "2020-01-01"}, ["1", "99V000001"]),
        ({"date_to": "2020-01-01"}, ["2"]),
    ],
)
async def test_structured_filters(
    seeded: None, client: AsyncClient, params: dict[str, str], expected: list[str]
) -> None:
    assert _ids(await _search(client, **params)) == expected


async def test_pagination_reports_total_and_is_date_ordered(
    seeded: None, client: AsyncClient
) -> None:
    body = await _search(client, limit=1, offset=1)

    assert (body["total"], body["limit"], body["offset"]) == (3, 1, 1)
    assert _ids(body) == ["99V000001"]


async def test_no_match_is_never_reported_as_safe(seeded: None, client: AsyncClient) -> None:
    body = await _search(client, q="zzqxv nonexistent widget")

    assert (body["total"], body["items"]) == (0, [])
    assert "not a safety determination" in body["disclaimer"]


async def _air_fryer_id(client: AsyncClient) -> int:
    recall_id: int = (await _search(client, model="AF-100X"))["items"][0]["id"]
    return recall_id


async def test_detail_exposes_evidence_and_provenance(seeded: None, client: AsyncClient) -> None:
    response = await client.get(f"/api/v1/recalls/{await _air_fryer_id(client)}")

    assert response.status_code == 200
    detail = response.json()
    provenance = detail["provenance"]
    assert (provenance["source"], provenance["source_record_id"]) == ("cpsc", "1")
    assert provenance["source_url"] == "https://example.invalid/1"
    assert provenance["agency"] == "U.S. Consumer Product Safety Commission"
    assert len(provenance["content_hash"]) == 64
    assert provenance["normalizer_version"] == "cpsc-1"
    assert detail["products"][0]["name"] == "Acme Air Fryers"
    assert detail["hazards"][0]["description"].startswith("The fryer can overheat")
    assert {"AF100X", "AF200X"} <= {i["normalized_value"] for i in detail["identifiers"]}


async def test_source_record_returns_exact_authoritative_payload(
    seeded: None, client: AsyncClient
) -> None:
    response = await client.get(f"/api/v1/recalls/{await _air_fryer_id(client)}/source-record")

    assert response.status_code == 200
    assert response.json()["payload"] == synthetic_payload(RecallID=1)


async def test_unknown_recall_is_404_problem(seeded: None, client: AsyncClient) -> None:
    response = await client.get("/api/v1/recalls/999999999")

    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/problem+json")


@pytest.mark.parametrize(
    "params",
    [
        {"limit": "500"},
        {"offset": "-1"},
        {"offset": "10001"},
        {"q": "x" * 201},
        {"source": "fda"},
        {"date_from": "2025-01-01", "date_to": "2024-01-01"},
    ],
)
async def test_invalid_parameters_are_rejected_as_problems(
    client: AsyncClient, params: dict[str, str]
) -> None:
    response = await client.get("/api/v1/recalls", params=params)

    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/problem+json")
