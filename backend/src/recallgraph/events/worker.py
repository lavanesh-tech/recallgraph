"""Outbox worker: claims pending events with FOR UPDATE SKIP LOCKED and delivers them.

Guarantees (all tested):
- Concurrent workers never claim the same event (SKIP LOCKED).
- A crash mid-batch rolls the whole batch back to pending: nothing is lost.
- Delivery is at-least-once to the transport; duplicates of the SAME alert are suppressed by
  the notification_deliveries unique key, and emails carry a deterministic Message-ID.
- Failures retry with exponential backoff; after MAX_ATTEMPTS an event is dead-lettered
  (status 'dead') and can be replayed explicitly.
"""

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from recallgraph.auth.models import User
from recallgraph.events.models import NotificationDelivery, OutboxEvent
from recallgraph.events.senders import NotificationSender
from recallgraph.inventory.models import InventoryItem
from recallgraph.matching.schemas import MATCH_DISCLAIMER
from recallgraph.radar.models import RadarAlert
from recallgraph.recalls.models import Recall

logger = structlog.get_logger(__name__)

ALERT_CREATED = "radar.alert.created"
MAX_ATTEMPTS = 5
BASE_BACKOFF_S = 30
MAX_BACKOFF_S = 3600


@dataclass(slots=True)
class WorkerStats:
    claimed: int = 0
    sent: int = 0
    duplicates: int = 0
    skipped: int = 0
    retried: int = 0
    dead: int = 0
    errors: list[str] = field(default_factory=list)


def backoff_seconds(attempts: int) -> int:
    return int(min(MAX_BACKOFF_S, BASE_BACKOFF_S * 2 ** max(0, attempts - 1)))


def alert_created_event(alert_id: uuid.UUID, user_id: uuid.UUID) -> OutboxEvent:
    return OutboxEvent(
        topic=ALERT_CREATED, payload={"alert_id": str(alert_id), "user_id": str(user_id)}
    )


async def _deliver_alert(
    session: AsyncSession, sender: NotificationSender, event_id: uuid.UUID, payload: dict[str, Any]
) -> str:
    alert_id = uuid.UUID(str(payload["alert_id"]))
    row = (
        await session.execute(
            select(User.email, InventoryItem.nickname, Recall.title, Recall.url, RadarAlert.tier)
            .select_from(RadarAlert)
            .join(User, User.id == RadarAlert.user_id)
            .join(InventoryItem, InventoryItem.id == RadarAlert.inventory_item_id)
            .join(Recall, Recall.id == RadarAlert.recall_id)
            .where(RadarAlert.id == alert_id)
        )
    ).one_or_none()
    if row is None:
        return "skipped"  # alert removed (e.g. item deleted) before delivery
    email, nickname, title, url, tier = row
    claimed = (
        await session.execute(
            pg_insert(NotificationDelivery)
            .values(
                id=uuid.uuid4(),
                alert_id=alert_id,
                channel="email",
                recipient=email,
                event_id=event_id,
            )
            .on_conflict_do_nothing(constraint="uq_notification_deliveries_alert_channel")
            .returning(NotificationDelivery.id)
        )
    ).scalar_one_or_none()
    if claimed is None:
        return "duplicate"
    await sender.send(
        to=email,
        subject=f"RecallGraph Radar: possible recall for your {nickname}",
        body=(
            f"Your saved item '{nickname}' matches an official recall ({tier}).\n\n"
            f"{title}\n{url or ''}\n\n{MATCH_DISCLAIMER}\n"
        ),
        message_id=f"<alert-{alert_id}@recallgraph.local>",
    )
    return "sent"


async def process_batch(
    session_factory: async_sessionmaker[AsyncSession],
    sender: NotificationSender,
    *,
    batch_size: int = 50,
    now: datetime | None = None,
) -> WorkerStats:
    now = now or datetime.now(UTC)
    stats = WorkerStats()
    async with session_factory() as session:
        claimed = (
            await session.execute(
                select(OutboxEvent.id, OutboxEvent.topic, OutboxEvent.payload, OutboxEvent.attempts)
                .where(OutboxEvent.status == "pending", OutboxEvent.available_at <= now)
                .order_by(OutboxEvent.created_at, OutboxEvent.id)
                .limit(batch_size)
                .with_for_update(skip_locked=True)
            )
        ).all()
        stats.claimed = len(claimed)
        for event_id, topic, payload, attempts in claimed:
            try:
                async with session.begin_nested():  # a failed event rolls back only itself
                    if topic != ALERT_CREATED:
                        raise ValueError(f"unknown topic {topic!r}")
                    outcome = await _deliver_alert(session, sender, event_id, payload)
            except Exception as exc:
                failures = attempts + 1
                is_dead = failures >= MAX_ATTEMPTS
                await session.execute(
                    update(OutboxEvent)
                    .where(OutboxEvent.id == event_id)
                    .values(
                        attempts=failures,
                        status="dead" if is_dead else "pending",
                        available_at=now + timedelta(seconds=backoff_seconds(failures)),
                        last_error=f"{type(exc).__name__}: {exc}"[:2000],
                    )
                )
                stats.dead += is_dead
                stats.retried += not is_dead
                stats.errors.append(type(exc).__name__)
                logger.warning("outbox_event_failed", event_id=str(event_id), dead=is_dead)
                continue
            await session.execute(
                update(OutboxEvent)
                .where(OutboxEvent.id == event_id)
                .values(status="delivered", delivered_at=now, last_error=None)
            )
            if outcome == "sent":
                stats.sent += 1
            elif outcome == "duplicate":
                stats.duplicates += 1
            else:
                stats.skipped += 1
        await session.commit()
    return stats


async def dead_letters(session: AsyncSession, limit: int = 100) -> list[dict[str, Any]]:
    rows = await session.execute(
        select(OutboxEvent.id, OutboxEvent.topic, OutboxEvent.attempts, OutboxEvent.last_error)
        .where(OutboxEvent.status == "dead")
        .order_by(OutboxEvent.created_at)
        .limit(limit)
    )
    return [{"id": str(i), "topic": t, "attempts": a, "last_error": e} for i, t, a, e in rows]


async def replay_dead(session: AsyncSession, event_id: uuid.UUID | None = None) -> int:
    conds = [OutboxEvent.status == "dead"]
    if event_id is not None:
        conds.append(OutboxEvent.id == event_id)
    result = await session.execute(
        update(OutboxEvent)
        .where(*conds)
        .values(status="pending", attempts=0, available_at=func.now())
        .returning(OutboxEvent.id)
    )
    replayed = len(result.all())
    await session.commit()
    return replayed


async def queue_depth(session: AsyncSession) -> dict[str, int]:
    rows = await session.execute(
        select(OutboxEvent.status, func.count()).group_by(OutboxEvent.status)
    )
    return {status: count for status, count in rows}
