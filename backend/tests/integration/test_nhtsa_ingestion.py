"""NHTSA ingestion + normalization against real PostgreSQL with a SYNTHETIC HTTP transport."""

from typing import Any

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from recallgraph.ingestion.runner import run_ingestion
from recallgraph.ingestion.sources.nhtsa import NhtsaAdapter, NhtsaRecallClient
from recallgraph.normalization.service import normalize_cpsc_records, normalize_source_records
from recallgraph.recalls.models import Recall
from tests.integration.test_normalization import _store
from tests.test_cpsc_normalizer import synthetic_payload
from tests.test_nhtsa_normalizer import synthetic_nhtsa

pytestmark = pytest.mark.integration


async def _no_sleep(_: float) -> None:
    return None


def _adapter(records: list[dict[str, Any]]) -> NhtsaAdapter:
    def handler(request: httpx.Request) -> httpx.Response:
        offset, limit = int(request.url.params["$offset"]), int(request.url.params["$limit"])
        return httpx.Response(200, json=records[offset : offset + limit])

    client = NhtsaRecallClient(httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    return NhtsaAdapter(client, page_size=2, sleep=_no_sleep)


async def test_nhtsa_ingest_is_idempotent_and_normalizes(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    records = [synthetic_nhtsa(nhtsa_id=f"99V00000{i}") for i in range(3)]

    first = await run_ingestion(session_factory, _adapter(records))
    second = await run_ingestion(session_factory, _adapter(records))
    counts = await normalize_source_records(session_factory, "nhtsa")

    assert (first.counts.inserted, first.windows) == (3, 2)
    assert (second.counts.inserted, second.counts.unchanged) == (0, 3)
    assert (counts.created, counts.rejected) == (3, 0)


async def test_same_record_id_in_two_sources_stays_separate(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await _store(session_factory, [synthetic_payload(RecallID=7)])
    await run_ingestion(session_factory, _adapter([synthetic_nhtsa(nhtsa_id="7")]))

    await normalize_cpsc_records(session_factory)
    await normalize_source_records(session_factory, "nhtsa")

    async with session_factory() as session:
        count = await session.execute(
            select(func.count()).select_from(Recall).where(Recall.source_record_id == "7")
        )
        assert count.scalar_one() == 2


async def test_unknown_source_is_rejected(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    with pytest.raises(ValueError, match="no normalizer"):
        await normalize_source_records(session_factory, "fda")
