"""Persistence for provenance: sources, ingestion runs and idempotent raw-record storage."""

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib.metadata import version
from typing import Any

from sqlalchemy import literal_column
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from recallgraph.provenance.hashing import content_hash
from recallgraph.provenance.models import IngestionRun, IngestionRunStatus, RawRecord, Source

# 1,000 rows x 8 columns stays far below PostgreSQL's 65,535 bind-parameter limit.
_UPSERT_CHUNK_SIZE = 1000


@dataclass(frozen=True, slots=True)
class SourceSpec:
    code: str
    name: str
    agency: str
    homepage_url: str


@dataclass(frozen=True, slots=True)
class RawRecordInput:
    source_record_id: str
    payload: dict[str, Any]
    source_url: str


@dataclass(frozen=True, slots=True)
class UpsertCounts:
    seen: int
    inserted: int
    unchanged: int


class SourceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert(self, spec: SourceSpec) -> Source:
        """Register a source by its stable code; re-registering updates its descriptive fields."""
        descriptive = {"name": spec.name, "agency": spec.agency, "homepage_url": spec.homepage_url}
        stmt = (
            pg_insert(Source)
            .values(code=spec.code, **descriptive)
            .on_conflict_do_update(index_elements=[Source.code], set_=descriptive)
            .returning(Source)
        )
        result = await self._session.scalars(stmt, execution_options={"populate_existing": True})
        return result.one()


class IngestionRunRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def start(self, source: Source, parameters: Mapping[str, Any]) -> IngestionRun:
        run = IngestionRun(
            source_id=source.id,
            status=IngestionRunStatus.RUNNING,
            pipeline_version=version("recallgraph"),
            parameters=dict(parameters),
        )
        self._session.add(run)
        await self._session.flush()
        return run

    async def finish(
        self,
        run: IngestionRun,
        *,
        status: IngestionRunStatus,
        counts: UpsertCounts,
        error_message: str | None = None,
    ) -> IngestionRun:
        run.status = status
        run.finished_at = datetime.now(UTC)
        run.records_seen = counts.seen
        run.records_inserted = counts.inserted
        run.records_unchanged = counts.unchanged
        run.error_message = error_message
        await self._session.flush()
        return run


class RawRecordRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert_many(
        self, *, source_id: int, run_id: uuid.UUID, records: Sequence[RawRecordInput]
    ) -> UpsertCounts:
        """Store new payload versions; for unchanged ones only advance last_seen_*.

        Re-running an ingestion with identical data inserts nothing (idempotent).
        """
        now = datetime.now(UTC)
        # ON CONFLICT cannot touch the same row twice in one statement: dedupe the batch first.
        unique_rows: dict[tuple[str, str], dict[str, Any]] = {}
        for record in records:
            digest = content_hash(record.payload)
            unique_rows.setdefault(
                (record.source_record_id, digest),
                {
                    "source_id": source_id,
                    "source_record_id": record.source_record_id,
                    "content_hash": digest,
                    "payload": record.payload,
                    "source_url": record.source_url,
                    "first_seen_run_id": run_id,
                    "last_seen_run_id": run_id,
                    "first_seen_at": now,
                    "last_seen_at": now,
                },
            )

        rows = list(unique_rows.values())
        inserted = 0
        for start in range(0, len(rows), _UPSERT_CHUNK_SIZE):
            stmt = pg_insert(RawRecord).values(rows[start : start + _UPSERT_CHUNK_SIZE])
            stmt = stmt.on_conflict_do_update(
                constraint="uq_raw_records_source_record_hash",
                set_={
                    "last_seen_run_id": stmt.excluded.last_seen_run_id,
                    "last_seen_at": stmt.excluded.last_seen_at,
                },
            )
            # xmax = 0 only for freshly inserted rows (PostgreSQL MVCC system column).
            flags: Sequence[bool] = (
                await self._session.scalars(stmt.returning(literal_column("xmax = 0")))
            ).all()
            inserted += sum(flags)

        return UpsertCounts(seen=len(records), inserted=inserted, unchanged=len(records) - inserted)
