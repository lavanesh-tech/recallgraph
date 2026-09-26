"""End-to-end CPSC ingestion against real PostgreSQL with a SYNTHETIC HTTP transport."""

from datetime import date
from typing import Any

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from recallgraph.ingestion.http import FetchError
from recallgraph.ingestion.runner import ingest_cpsc
from recallgraph.ingestion.sources.cpsc import CpscRecallClient, DateWindow
from recallgraph.provenance.models import IngestionRun, RawRecord

pytestmark = pytest.mark.integration

WINDOWS = [
    DateWindow(date(2024, 1, 1), date(2024, 12, 31)),
    DateWindow(date(2025, 1, 1), date(2025, 12, 31)),
]


def _synthetic_records(year: str) -> list[dict[str, Any]]:
    base = 1000 if year == "2024" else 2000
    return [
        {
            "RecallID": base + i,
            "Title": f"SYNTHETIC recall {base + i}",
            "RecallDate": f"{year}-06-01T00:00:00",
            "URL": f"https://example.invalid/recalls/{base + i}",
        }
        for i in range(3)
    ]


def _synthetic_api() -> CpscRecallClient:
    def handler(request: httpx.Request) -> httpx.Response:
        year = request.url.params["RecallDateStart"][:4]
        return httpx.Response(200, json=_synthetic_records(year))

    return CpscRecallClient(httpx.AsyncClient(transport=httpx.MockTransport(handler)))


async def _no_sleep(_: float) -> None:
    return None


async def test_ingestion_is_idempotent_across_runs(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    first = await ingest_cpsc(session_factory, _synthetic_api(), WINDOWS, sleep=_no_sleep)
    second = await ingest_cpsc(session_factory, _synthetic_api(), WINDOWS, sleep=_no_sleep)

    assert (first.counts.seen, first.counts.inserted) == (6, 6)
    assert (second.counts.seen, second.counts.inserted, second.counts.unchanged) == (6, 0, 6)
    async with session_factory() as session:
        stored = await session.execute(select(func.count()).select_from(RawRecord))
        statuses = await session.execute(select(IngestionRun.status))
        assert stored.scalar_one() == 6
        assert sorted(statuses.scalars()) == ["succeeded", "succeeded"]


async def test_failed_run_is_recorded_with_error_and_partial_counts(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.params["RecallDateStart"].startswith("2025"):
            return httpx.Response(503)
        return httpx.Response(200, json=_synthetic_records("2024"))

    client = CpscRecallClient(
        httpx.AsyncClient(transport=httpx.MockTransport(handler)), max_attempts=2, sleep=_no_sleep
    )

    with pytest.raises(FetchError):
        await ingest_cpsc(session_factory, client, WINDOWS, sleep=_no_sleep)

    async with session_factory() as session:
        run = (await session.execute(select(IngestionRun))).scalar_one()
        stored = await session.execute(select(func.count()).select_from(RawRecord))
    assert run.status == "failed"
    assert run.error_message is not None and "HTTP 503" in run.error_message
    assert (run.records_seen, run.records_inserted) == (3, 3)
    assert stored.scalar_one() == 3  # the successful 2024 window was committed
