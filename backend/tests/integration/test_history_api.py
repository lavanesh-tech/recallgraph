"""Safety-history API against real PostgreSQL. All records are SYNTHETIC."""

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
    older_fryer = synthetic_payload(
        RecallID=3, RecallDate="2021-05-01T00:00:00", Importers=[], ProductUPCs=[]
    )
    await _store(session_factory, [synthetic_payload(RecallID=1), HEATER, older_fryer])
    await normalize_cpsc_records(session_factory)
    await run_ingestion(session_factory, _adapter([synthetic_nhtsa()]))
    await normalize_source_records(session_factory, "nhtsa")


async def _get(client: AsyncClient, url: str, **params: str) -> dict[str, Any]:
    response = await client.get(url, params=params)
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


async def _company_id(client: AsyncClient, q: str) -> int:
    company_id: int = (await _get(client, "/api/v1/companies", q=q))["items"][0]["id"]
    return company_id


async def test_company_search_ranks_by_recall_count(catalog: None, client: AsyncClient) -> None:
    items = (await _get(client, "/api/v1/companies", q="acme"))["items"]

    assert [(i["name"], i["recall_count"]) for i in items] == [
        ("Acme Manufacturing Co., Ltd.", 2),
        ("Acme USA LLC", 1),
    ]


async def test_company_history_timeline_roles_and_recent(
    catalog: None, client: AsyncClient
) -> None:
    company_id = await _company_id(client, "acme manufacturing")

    body = await _get(client, f"/api/v1/companies/{company_id}/history")

    assert body["total_recalls"] == 2
    assert (body["first_recall_date"], body["last_recall_date"]) == ("2021-05-01", "2026-09-24")
    assert body["by_year"] == [
        {"year": 2021, "source": "cpsc", "count": 1},
        {"year": 2026, "source": "cpsc", "count": 1},
    ]
    assert body["by_role"] == [{"role": "manufacturer", "count": 2}]
    assert [r["source_record_id"] for r in body["recent_recalls"]] == ["1", "3"]
    assert "not a safety rating" in body["disclaimer"]


async def test_unknown_company_is_404_problem(client: AsyncClient) -> None:
    response = await client.get("/api/v1/companies/2147483000/history")

    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/problem+json")


async def test_timeline_counts_per_year_and_source(catalog: None, client: AsyncClient) -> None:
    body = await _get(client, "/api/v1/recalls/timeline")

    assert body["total"] == 4
    assert body["buckets"] == [
        {"year": 2019, "source": "cpsc", "count": 1},
        {"year": 2021, "source": "cpsc", "count": 1},
        {"year": 2026, "source": "cpsc", "count": 1},
        {"year": 2026, "source": "nhtsa", "count": 1},
    ]


async def test_product_timeline_reuses_search_filters(catalog: None, client: AsyncClient) -> None:
    body = await _get(client, "/api/v1/recalls/timeline", q="air fryer")

    assert body["total"] == 2
    assert [b["year"] for b in body["buckets"]] == [2021, 2026]
    assert "not a safety determination" in body["disclaimer"]


@pytest.mark.parametrize(
    ("url", "params"),
    [
        ("/api/v1/companies", {"q": "a"}),
        ("/api/v1/companies", {"q": "acme", "limit": "51"}),
        ("/api/v1/recalls/timeline", {"date_from": "2025-01-01", "date_to": "2024-01-01"}),
    ],
)
async def test_invalid_history_parameters(
    client: AsyncClient, url: str, params: dict[str, str]
) -> None:
    response = await client.get(url, params=params)

    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/problem+json")
