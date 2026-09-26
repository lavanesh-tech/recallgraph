"""Runs an ingestion: fetch windows, store raw records idempotently, record the run outcome."""

import asyncio
import time
import uuid
from collections.abc import Sequence
from dataclasses import dataclass

import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from recallgraph.ingestion.http import Sleep
from recallgraph.ingestion.sources.cpsc import (
    CPSC_RECALL_API_URL,
    CPSC_SOURCE,
    CpscRecallClient,
    DateWindow,
    to_raw_input,
)
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


async def ingest_cpsc(
    session_factory: async_sessionmaker[AsyncSession],
    client: CpscRecallClient,
    windows: Sequence[DateWindow],
    *,
    pause_s: float = 0.5,
    sleep: Sleep = asyncio.sleep,
) -> IngestionSummary:
    """Each window is committed separately, so a later failure keeps earlier progress.

    A failed run is still recorded (status=failed, error, partial counts) and the error re-raised.
    """
    started = time.perf_counter()
    totals = UpsertCounts(0, 0, 0)
    async with session_factory() as session:
        runs = IngestionRunRepository(session)
        source = await SourceRepository(session).upsert(CPSC_SOURCE)
        source_id = source.id
        run = await runs.start(
            source,
            {
                "api": CPSC_RECALL_API_URL,
                "windows": [[w.start.isoformat(), w.end.isoformat()] for w in windows],
            },
        )
        run_id = run.id
        await session.commit()
        logger.info("ingestion_started", source=CPSC_SOURCE.code, run_id=str(run_id))

        try:
            for index, window in enumerate(windows):
                if index:
                    await sleep(pause_s)  # be polite to the public API
                records = await client.fetch_window(window)
                inputs = [to_raw_input(r, fallback_url=window.query_url()) for r in records]
                counts = await RawRecordRepository(session).upsert_many(
                    source_id=source_id, run_id=run_id, records=inputs
                )
                await session.commit()
                totals = _add(totals, counts)
                logger.info(
                    "ingestion_window_done",
                    run_id=str(run_id),
                    window=window.start.isoformat(),
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
            logger.error("ingestion_failed", run_id=str(run_id), error_type=type(exc).__name__)
            raise

        await runs.finish(run, status=IngestionRunStatus.SUCCEEDED, counts=totals)
        await session.commit()

    summary = IngestionSummary(
        run_id=run_id,
        source=CPSC_SOURCE.code,
        status=IngestionRunStatus.SUCCEEDED,
        windows=len(windows),
        counts=totals,
        duration_s=round(time.perf_counter() - started, 3),
    )
    logger.info("ingestion_succeeded", run_id=str(run_id), seen=totals.seen)
    return summary
