"""Provenance repositories against real PostgreSQL. All payloads here are SYNTHETIC test data."""

from dataclasses import replace
from typing import Any

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from recallgraph.provenance.models import IngestionRunStatus, RawRecord, Source
from recallgraph.provenance.repository import (
    IngestionRunRepository,
    RawRecordInput,
    RawRecordRepository,
    SourceRepository,
    SourceSpec,
    UpsertCounts,
)

pytestmark = pytest.mark.integration

SYNTHETIC_SOURCE = SourceSpec(
    code="synthetic-test",
    name="Synthetic test source (not real government data)",
    agency="SYNTHETIC",
    homepage_url="https://example.invalid/",
)


def _record(record_id: str, **payload: Any) -> RawRecordInput:
    return RawRecordInput(
        source_record_id=record_id,
        payload={"synthetic": True, "id": record_id, **payload},
        source_url=f"https://example.invalid/records/{record_id}",
    )


async def _source(session: AsyncSession) -> Source:
    return await SourceRepository(session).upsert(SYNTHETIC_SOURCE)


async def _count_raw(session: AsyncSession) -> int:
    return (await session.execute(select(func.count()).select_from(RawRecord))).scalar_one()


async def test_source_upsert_is_idempotent_and_updates_descriptive_fields(
    db_session: AsyncSession,
) -> None:
    first = await _source(db_session)
    renamed = replace(SYNTHETIC_SOURCE, name="Renamed synthetic source")
    second = await SourceRepository(db_session).upsert(renamed)

    assert second.id == first.id
    assert second.name == "Renamed synthetic source"
    assert (await db_session.execute(select(func.count()).select_from(Source))).scalar_one() == 1


async def test_reingesting_identical_records_inserts_nothing(db_session: AsyncSession) -> None:
    source = await _source(db_session)
    runs, raw = IngestionRunRepository(db_session), RawRecordRepository(db_session)
    batch = [_record("R-1", title="A"), _record("R-2", title="B"), _record("R-3", title="C")]

    run1 = await runs.start(source, {"synthetic": True})
    first = await raw.upsert_many(source_id=source.id, run_id=run1.id, records=batch)
    run2 = await runs.start(source, {"synthetic": True})
    second = await raw.upsert_many(source_id=source.id, run_id=run2.id, records=batch)

    assert first == UpsertCounts(seen=3, inserted=3, unchanged=0)
    assert second == UpsertCounts(seen=3, inserted=0, unchanged=3)
    assert await _count_raw(db_session) == 3
    row = (
        await db_session.execute(select(RawRecord).where(RawRecord.source_record_id == "R-1"))
    ).scalar_one()
    assert (row.first_seen_run_id, row.last_seen_run_id) == (run1.id, run2.id)


async def test_key_order_does_not_create_a_new_version(db_session: AsyncSession) -> None:
    source = await _source(db_session)
    run = await IngestionRunRepository(db_session).start(source, {})
    raw = RawRecordRepository(db_session)
    a = RawRecordInput("R-1", {"x": 1, "y": 2}, "https://example.invalid/R-1")
    b = RawRecordInput("R-1", {"y": 2, "x": 1}, "https://example.invalid/R-1")

    await raw.upsert_many(source_id=source.id, run_id=run.id, records=[a])
    counts = await raw.upsert_many(source_id=source.id, run_id=run.id, records=[b])

    assert counts.inserted == 0
    assert await _count_raw(db_session) == 1


async def test_changed_payload_is_stored_as_a_new_version(db_session: AsyncSession) -> None:
    source = await _source(db_session)
    run = await IngestionRunRepository(db_session).start(source, {})
    raw = RawRecordRepository(db_session)

    await raw.upsert_many(source_id=source.id, run_id=run.id, records=[_record("R-1", v=1)])
    counts = await raw.upsert_many(
        source_id=source.id, run_id=run.id, records=[_record("R-1", v=2)]
    )

    assert counts.inserted == 1
    versions = await db_session.execute(
        select(func.count()).select_from(RawRecord).where(RawRecord.source_record_id == "R-1")
    )
    assert versions.scalar_one() == 2


async def test_duplicates_within_one_batch_are_stored_once(db_session: AsyncSession) -> None:
    source = await _source(db_session)
    run = await IngestionRunRepository(db_session).start(source, {})

    counts = await RawRecordRepository(db_session).upsert_many(
        source_id=source.id, run_id=run.id, records=[_record("R-1"), _record("R-1")]
    )

    assert counts == UpsertCounts(seen=2, inserted=1, unchanged=1)
    assert await _count_raw(db_session) == 1


async def test_ingestion_run_lifecycle_records_outcome(db_session: AsyncSession) -> None:
    source = await _source(db_session)
    runs = IngestionRunRepository(db_session)

    run = await runs.start(source, {"page_size": 100})
    assert run.status == IngestionRunStatus.RUNNING
    assert run.finished_at is None

    await runs.finish(
        run,
        status=IngestionRunStatus.FAILED,
        counts=UpsertCounts(seen=0, inserted=0, unchanged=0),
        error_message="synthetic upstream timeout",
    )
    await db_session.commit()
    await db_session.refresh(run)

    assert run.status == "failed"
    assert run.finished_at is not None
    assert run.error_message == "synthetic upstream timeout"
    assert run.parameters == {"page_size": 100}
    assert run.pipeline_version


async def test_database_rejects_invalid_run_status(db_session: AsyncSession) -> None:
    source = await _source(db_session)
    with pytest.raises(IntegrityError):
        await db_session.execute(
            text(
                "INSERT INTO ingestion_runs (id, source_id, status, pipeline_version) "
                "VALUES (gen_random_uuid(), :source_id, 'bogus', '0')"
            ),
            {"source_id": source.id},
        )
