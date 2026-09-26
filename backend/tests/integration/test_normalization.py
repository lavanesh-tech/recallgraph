"""Normalization service against real PostgreSQL. All payloads are SYNTHETIC."""

from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import selectinload

from recallgraph.ingestion.sources.cpsc import CPSC_SOURCE
from recallgraph.normalization.service import normalize_cpsc_records
from recallgraph.provenance.models import RawRecord
from recallgraph.provenance.repository import (
    IngestionRunRepository,
    RawRecordInput,
    RawRecordRepository,
    SourceRepository,
)
from recallgraph.recalls.models import Company, Recall, RecallCompany
from tests.test_cpsc_normalizer import synthetic_payload

pytestmark = pytest.mark.integration


async def _store(factory: async_sessionmaker[AsyncSession], payloads: list[dict[str, Any]]) -> None:
    async with factory() as session:
        source = await SourceRepository(session).upsert(CPSC_SOURCE)
        run = await IngestionRunRepository(session).start(source, {"synthetic": True})
        await RawRecordRepository(session).upsert_many(
            source_id=source.id,
            run_id=run.id,
            records=[
                RawRecordInput(str(p["RecallID"]), p, f"https://example.invalid/{p['RecallID']}")
                for p in payloads
            ],
        )
        await session.commit()


async def _count(factory: async_sessionmaker[AsyncSession], model: type[Any]) -> int:
    async with factory() as session:
        count: int = (await session.execute(select(func.count()).select_from(model))).scalar_one()
    return count


async def test_normalizes_once_and_is_idempotent(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await _store(session_factory, [synthetic_payload(RecallID=1), synthetic_payload(RecallID=2)])

    first = await normalize_cpsc_records(session_factory)
    second = await normalize_cpsc_records(session_factory)

    assert (first.seen, first.created, first.unchanged) == (2, 2, 0)
    assert (second.seen, second.created, second.updated, second.unchanged) == (2, 0, 0, 2)
    assert await _count(session_factory, Recall) == 2


async def test_new_raw_version_updates_recall_and_replaces_children(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await _store(session_factory, [synthetic_payload(RecallID=1)])
    await normalize_cpsc_records(session_factory)
    await _store(session_factory, [synthetic_payload(RecallID=1, Title="SYNTHETIC updated title")])

    counts = await normalize_cpsc_records(session_factory)

    assert (counts.updated, counts.created) == (1, 0)
    async with session_factory() as session:
        recall = (
            await session.execute(select(Recall).options(selectinload(Recall.products)))
        ).scalar_one()
        latest_raw = (
            await session.execute(select(RawRecord.id).order_by(RawRecord.id.desc()).limit(1))
        ).scalar_one()
    assert recall.title == "SYNTHETIC updated title"
    assert recall.raw_record_id == latest_raw  # provenance points at the newest version
    assert len(recall.products) == 1  # replaced, not duplicated


async def test_companies_are_deduplicated_across_recalls(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await _store(session_factory, [synthetic_payload(RecallID=1), synthetic_payload(RecallID=2)])

    await normalize_cpsc_records(session_factory)

    assert await _count(session_factory, Company) == 2  # manufacturer + importer
    assert await _count(session_factory, RecallCompany) == 4


async def test_invalid_records_are_counted_not_fatal(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await _store(
        session_factory, [synthetic_payload(RecallID=1), synthetic_payload(RecallID=2, Title="")]
    )

    counts = await normalize_cpsc_records(session_factory)

    assert (counts.created, counts.rejected) == (1, 1)


async def test_requires_ingested_source(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    with pytest.raises(LookupError):
        await normalize_cpsc_records(session_factory)
