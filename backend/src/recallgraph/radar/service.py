"""Recall Radar: turn new official recalls and new/changed inventory items into alerts.

One run, in ONE transaction guarded by a PostgreSQL advisory lock (no concurrent runs):
  1. Reverse scan: recalls normalized since the last successful run (the recall watermark)
     are scored against every inventory item with the deterministic matching engine.
  2. Forward scan: inventory items created/updated since the last run are matched against
     the whole catalog.
Only strict tiers (identifier_match, likely) create alerts. Alerts are unique per
(item, recall), so re-scanning is safe; watermarks overlap by OVERLAP to cover rows committed
late by concurrent writers.
"""

import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from recallgraph.inventory.models import InventoryItem
from recallgraph.inventory.service import to_match_query
from recallgraph.matching.candidates import load_profiles
from recallgraph.matching.engine import ENGINE_VERSION, MatchResult, score_candidate
from recallgraph.matching.service import match_product
from recallgraph.radar.models import RadarAlert, RadarRun
from recallgraph.recalls.models import Recall

logger = structlog.get_logger(__name__)

RADAR_LOCK_KEY = 7_202_617
ALERT_TIERS = frozenset({"identifier_match", "likely"})
OVERLAP = timedelta(minutes=5)
FORWARD_MATCH_LIMIT = 20


@dataclass(frozen=True, slots=True)
class RadarRunSummary:
    run_id: uuid.UUID | None
    status: str
    recalls_scanned: int
    items_scanned: int
    alerts_created: int
    duration_s: float


async def _alert(session: AsyncSession, item: InventoryItem, result: MatchResult) -> int:
    stmt = (
        pg_insert(RadarAlert)
        .values(
            id=uuid.uuid4(),
            user_id=item.user_id,
            inventory_item_id=item.id,
            recall_id=result.profile.recall_id,
            tier=result.tier,
            score=result.score,
            engine_version=ENGINE_VERSION,
        )
        .on_conflict_do_nothing(constraint="uq_radar_alerts_item_recall")
        .returning(RadarAlert.id)
    )
    created = (await session.execute(stmt)).scalar_one_or_none()
    return 1 if created is not None else 0


async def _scan(session: AsyncSession, started: datetime) -> RadarRun:
    previous = await session.scalar(
        select(RadarRun)
        .where(RadarRun.status == "succeeded")
        .order_by(RadarRun.started_at.desc())
        .limit(1)
    )
    alerts = 0

    # 1. Reverse scan: new recalls x all items. The first run only sets a baseline, because
    #    existing matches for existing items are produced by the forward scan below.
    recall_ids: list[int] = []
    if previous is None or previous.recall_watermark is None:
        next_recall_watermark = await session.scalar(select(func.max(Recall.normalized_at)))
    else:
        rows = (
            await session.execute(
                select(Recall.id, Recall.normalized_at).where(
                    Recall.normalized_at > previous.recall_watermark - OVERLAP
                )
            )
        ).all()
        recall_ids = [recall_id for recall_id, _ in rows]
        next_recall_watermark = max([previous.recall_watermark, *(ts for _, ts in rows)])
    if recall_ids:
        profiles = await load_profiles(session, recall_ids)
        items = (await session.execute(select(InventoryItem))).scalars().all()
        for item in items:
            query = to_match_query(item)
            for profile in profiles:
                result = score_candidate(query, profile)
                if result is not None and result.tier in ALERT_TIERS:
                    alerts += await _alert(session, item, result)

    # 2. Forward scan: new or changed items x whole catalog.
    stmt = select(InventoryItem)
    if previous is not None and previous.item_watermark is not None:
        stmt = stmt.where(InventoryItem.updated_at > previous.item_watermark - OVERLAP)
    changed_items = (await session.execute(stmt)).scalars().all()
    for item in changed_items:
        outcome = await match_product(session, to_match_query(item), FORWARD_MATCH_LIMIT)
        for result in outcome.results:
            if result.tier in ALERT_TIERS:
                alerts += await _alert(session, item, result)

    return RadarRun(
        started_at=started,
        finished_at=datetime.now(UTC),
        status="succeeded",
        recall_watermark=next_recall_watermark,
        item_watermark=started,
        recalls_scanned=len(recall_ids),
        items_scanned=len(changed_items),
        alerts_created=alerts,
    )


async def run_radar(session_factory: async_sessionmaker[AsyncSession]) -> RadarRunSummary:
    started = datetime.now(UTC)
    clock = time.perf_counter()
    async with session_factory() as session:
        locked = await session.scalar(
            text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": RADAR_LOCK_KEY}
        )
        if not locked:
            logger.warning("radar_run_skipped", reason="another run holds the lock")
            return RadarRunSummary(None, "skipped", 0, 0, 0, round(time.perf_counter() - clock, 3))
        try:
            run = await _scan(session, started)
            session.add(run)
            await session.commit()  # releases the transaction-scoped advisory lock
        except Exception as exc:
            await session.rollback()
            session.add(
                RadarRun(
                    started_at=started,
                    finished_at=datetime.now(UTC),
                    status="failed",
                    error_message=f"{type(exc).__name__}: {exc}"[:2000],
                )
            )
            await session.commit()
            logger.error("radar_run_failed", error_type=type(exc).__name__)
            raise
    summary = RadarRunSummary(
        run_id=run.id,
        status=run.status,
        recalls_scanned=run.recalls_scanned,
        items_scanned=run.items_scanned,
        alerts_created=run.alerts_created,
        duration_s=round(time.perf_counter() - clock, 3),
    )
    logger.info("radar_run_succeeded", alerts_created=summary.alerts_created)
    return summary
