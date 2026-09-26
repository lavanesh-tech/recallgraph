"""Outbox + worker reliability against real PostgreSQL (SYNTHETIC users and recalls)."""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from recallgraph.auth.models import User
from recallgraph.events.models import NotificationDelivery, OutboxEvent
from recallgraph.events.worker import (
    ALERT_CREATED,
    MAX_ATTEMPTS,
    process_batch,
    replay_dead,
)
from recallgraph.inventory.models import InventoryItem
from recallgraph.normalization.service import normalize_cpsc_records
from recallgraph.radar.models import RadarAlert
from recallgraph.radar.service import run_radar
from tests.integration.test_normalization import _store
from tests.test_cpsc_normalizer import synthetic_payload

pytestmark = pytest.mark.integration


class FakeSender:
    def __init__(self, failures: int = 0, crash: bool = False) -> None:
        self.failures = failures
        self.crash = crash
        self.sent: list[str] = []

    async def send(self, *, to: str, subject: str, body: str, message_id: str) -> None:
        if self.crash:
            raise SimulatedCrash
        if self.failures:
            self.failures -= 1
            raise ConnectionError("synthetic SMTP outage")
        self.sent.append(message_id)


class SimulatedCrash(BaseException):  # like a killed process: not caught as a normal error
    pass


@pytest.fixture
async def alert_id(session_factory: async_sessionmaker[AsyncSession]) -> uuid.UUID:
    await _store(session_factory, [synthetic_payload(RecallID=1)])
    await normalize_cpsc_records(session_factory)
    async with session_factory() as session:
        user = User(email="alice@example.com", password_hash="not-used-in-this-test")
        session.add(user)
        await session.flush()
        session.add(InventoryItem(user_id=user.id, nickname="Air fryer", model="AF-100X"))
        await session.commit()
    await run_radar(session_factory)
    async with session_factory() as session:
        found: uuid.UUID = (await session.execute(select(RadarAlert.id))).scalar_one()
    return found


async def _statuses(factory: async_sessionmaker[AsyncSession]) -> list[tuple[str, int]]:
    async with factory() as session:
        rows = await session.execute(
            select(OutboxEvent.status, OutboxEvent.attempts).order_by(OutboxEvent.created_at)
        )
        return [(status, attempts) for status, attempts in rows]


async def _deliveries(factory: async_sessionmaker[AsyncSession]) -> int:
    async with factory() as session:
        count: int = (
            await session.execute(select(func.count()).select_from(NotificationDelivery))
        ).scalar_one()
    return count


async def _publish_duplicates(
    factory: async_sessionmaker[AsyncSession], alert: uuid.UUID, n: int
) -> None:
    async with factory() as session:
        for _ in range(n):
            session.add(OutboxEvent(topic=ALERT_CREATED, payload={"alert_id": str(alert)}))
        await session.commit()


async def test_radar_writes_alert_and_event_atomically(
    alert_id: uuid.UUID, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    async with session_factory() as session:
        event = (await session.execute(select(OutboxEvent))).scalar_one()
    assert (event.topic, event.status) == (ALERT_CREATED, "pending")
    assert event.payload["alert_id"] == str(alert_id)


async def test_worker_delivers_once(
    alert_id: uuid.UUID, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    sender = FakeSender()

    first = await process_batch(session_factory, sender)
    second = await process_batch(session_factory, sender)

    assert (first.claimed, first.sent, second.claimed) == (1, 1, 0)
    assert sender.sent == [f"<alert-{alert_id}@recallgraph.local>"]
    assert await _statuses(session_factory) == [("delivered", 0)]
    assert await _deliveries(session_factory) == 1


async def test_duplicate_events_send_one_notification(
    alert_id: uuid.UUID, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    await _publish_duplicates(session_factory, alert_id, 2)
    sender = FakeSender()

    stats = await process_batch(session_factory, sender)

    assert (stats.claimed, stats.sent, stats.duplicates) == (3, 1, 2)
    assert len(sender.sent) == 1
    assert {s for s, _ in await _statuses(session_factory)} == {"delivered"}


async def test_retries_with_backoff_then_dead_letter_then_replay(
    alert_id: uuid.UUID, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    failing = FakeSender(failures=100)
    now = datetime.now(UTC) + timedelta(seconds=2)
    early = await process_batch(session_factory, failing, now=now)
    not_yet = await process_batch(session_factory, failing, now=now + timedelta(seconds=10))
    assert (early.retried, not_yet.claimed) == (1, 0)  # backoff delays the retry

    for attempt in range(2, MAX_ATTEMPTS + 1):
        await process_batch(session_factory, failing, now=now + timedelta(days=attempt))
    assert await _statuses(session_factory) == [("dead", MAX_ATTEMPTS)]
    assert await _deliveries(session_factory) == 0  # failed sends leave no delivery record
    assert (
        await process_batch(session_factory, failing, now=now + timedelta(days=30))
    ).claimed == 0

    async with session_factory() as session:
        assert await replay_dead(session) == 1
    healthy = FakeSender()
    stats = await process_batch(session_factory, healthy, now=now + timedelta(days=31))
    assert stats.sent == 1
    assert await _statuses(session_factory) == [("delivered", 0)]


async def test_crash_mid_batch_loses_nothing(
    alert_id: uuid.UUID, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    with pytest.raises(SimulatedCrash):
        await process_batch(session_factory, FakeSender(crash=True))

    assert await _statuses(session_factory) == [("pending", 0)]
    assert await _deliveries(session_factory) == 0
    assert (await process_batch(session_factory, FakeSender())).sent == 1


async def test_concurrent_workers_never_claim_the_same_event(
    alert_id: uuid.UUID, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    await _publish_duplicates(session_factory, alert_id, 39)  # 40 events in total
    sender = FakeSender()

    results = await asyncio.gather(
        *(process_batch(session_factory, sender, batch_size=10) for _ in range(4))
    )
    while (extra := await process_batch(session_factory, sender, batch_size=10)).claimed:
        results.append(extra)

    assert sum(r.claimed for r in results) == 40  # each event claimed exactly once
    assert len(sender.sent) == 1
    assert {s for s, _ in await _statuses(session_factory)} == {"delivered"}


async def test_alert_deleted_before_delivery_is_skipped(
    alert_id: uuid.UUID, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    async with session_factory() as session:
        item = (await session.execute(select(InventoryItem))).scalar_one()
        await session.delete(item)  # cascades to the alert
        await session.commit()
    sender = FakeSender()

    stats = await process_batch(session_factory, sender)

    assert (stats.skipped, sender.sent) == (1, [])
