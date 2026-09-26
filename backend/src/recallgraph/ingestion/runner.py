"""Source-agnostic ingestion: fetch batches, store raw records idempotently, record the run."""

import asyncio
import time
import uuid
from collections.abc import Sequence
from dataclasses import dataclass

import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from recallgraph.ingestion.base import SourceAdapter
from recallgraph.ingestion.http import Sleep
from recallgraph.ingestion.sources.cpsc import CpscAdapter, CpscRecallClient, DateWindow
from recallgraph.provenance.models import IngestionRunStatus
from recallgraph.provenance.repository import (
    IngestionRunRepository,
    RawRecordRepository,
    SourceRepository,
    UpsertCounts,
)

logger = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class IngestionSummary:
    run_id: uuid.UUID
    source: str
    status: str
    windows: int
    counts: UpsertCounts
    duration_s: float


def _add(a: UpsertCounts, b: UpsertCounts) -> UpsertCounts:
    return UpsertCounts(a.seen + b.seen, a.inserted + b.inserted, a.unchanged + b.unchanged)


async def run_ingestion(
    session_factory: async_sessionmaker[AsyncSession], adapter: SourceAdapter
) -> IngestionSummary:
    """Each batch is committed separately, so a later failure keeps earlier progress.

    A failed run is still recorded (status=failed, error, partial counts) and the error re-raised.
    """
    started = time.perf_counter()
    totals = UpsertCounts(0, 0, 0)
    batches = 0
    code = adapter.spec.code
    async with session_factory() as session:
        runs = IngestionRunRepository(session)
        source = await SourceRepository(session).upsert(adapter.spec)
        source_id = source.id
        run = await runs.start(source, adapter.parameters())
        run_id = run.id
        await session.commit()
        logger.info("ingestion_started", source=code, run_id=str(run_id))

        try:
            async for batch in adapter.batches():
                counts = await RawRecordRepository(session).upsert_many(
                    source_id=source_id, run_id=run_id, records=batch.records
                )
                await session.commit()
                totals = _add(totals, counts)
                batches += 1
                logger.info(
                    "ingestion_batch_done",
                    source=code,
                    batch=batch.label,
                    seen=counts.seen,
                    inserted=counts.inserted,
                )
        except Exception as exc:
            await session.rollback()
            await session.refresh(run)
            await runs.finish(
                run,
                status=IngestionRunStatus.FAILED,
                counts=totals,
                error_message=f"{type(exc).__name__}: {exc}"[:2000],
            )
            await session.commit()
            logger.error("ingestion_failed", source=code, error_type=type(exc).__name__)
            raise

        await runs.finish(run, status=IngestionRunStatus.SUCCEEDED, counts=totals)
        await session.commit()

    logger.info("ingestion_succeeded", source=code, run_id=str(run_id), seen=totals.seen)
    return IngestionSummary(
        run_id=run_id,
        source=code,
        status=IngestionRunStatus.SUCCEEDED,
        windows=batches,
        counts=totals,
        duration_s=round(time.perf_counter() - started, 3),
    )


async def ingest_cpsc(
    session_factory: async_sessionmaker[AsyncSession],
    client: CpscRecallClient,
    windows: Sequence[DateWindow],
    *,
    pause_s: float = 0.5,
    sleep: Sleep = asyncio.sleep,
) -> IngestionSummary:
    adapter = CpscAdapter(client, windows, pause_s=pause_s, sleep=sleep)
    return await run_ingestion(session_factory, adapter)
