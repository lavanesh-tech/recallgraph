"""Alert queries for the notifications API. Always scoped to the owning user."""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from recallgraph.inventory.models import InventoryItem
from recallgraph.provenance.models import Source
from recallgraph.radar.models import RadarAlert
from recallgraph.recalls.models import Recall
from recallgraph.search.service import _companies


@dataclass(frozen=True, slots=True)
class AlertView:
    alert: RadarAlert
    item_nickname: str
    recall: Recall
    source: str
    companies: list[tuple[str, str]]


async def unread_count(session: AsyncSession, user_id: uuid.UUID) -> int:
    count: int = (
        await session.execute(
            select(func.count())
            .select_from(RadarAlert)
            .where(RadarAlert.user_id == user_id, RadarAlert.read_at.is_(None))
        )
    ).scalar_one()
    return count


async def list_alerts(
    session: AsyncSession, user_id: uuid.UUID, *, unread_only: bool, limit: int, offset: int
) -> tuple[int, list[AlertView]]:
    conds = [RadarAlert.user_id == user_id]
    if unread_only:
        conds.append(RadarAlert.read_at.is_(None))
    total: int = (
        await session.execute(select(func.count()).select_from(RadarAlert).where(*conds))
    ).scalar_one()
    rows = (
        await session.execute(
            select(RadarAlert, InventoryItem.nickname, Recall, Source.code)
            .join(InventoryItem, InventoryItem.id == RadarAlert.inventory_item_id)
            .join(Recall, Recall.id == RadarAlert.recall_id)
            .join(Source, Source.id == Recall.source_id)
            .where(*conds)
            .order_by(RadarAlert.created_at.desc(), RadarAlert.id)
            .limit(limit)
            .offset(offset)
        )
    ).all()
    companies = await _companies(session, [recall.id for _, _, recall, _ in rows])
    return total, [
        AlertView(alert, nickname, recall, source, companies.get(recall.id, []))
        for alert, nickname, recall, source in rows
    ]


async def mark_read(session: AsyncSession, user_id: uuid.UUID, alert_id: uuid.UUID) -> bool:
    """False if the alert does not exist or belongs to another user."""
    owned = await session.scalar(
        select(RadarAlert.id).where(RadarAlert.id == alert_id, RadarAlert.user_id == user_id)
    )
    if owned is None:
        return False
    await session.execute(
        update(RadarAlert)
        .where(RadarAlert.id == alert_id, RadarAlert.read_at.is_(None))
        .values(read_at=datetime.now(UTC))
    )
    await session.commit()
    return True


async def mark_all_read(session: AsyncSession, user_id: uuid.UUID) -> int:
    result = await session.execute(
        update(RadarAlert)
        .where(RadarAlert.user_id == user_id, RadarAlert.read_at.is_(None))
        .values(read_at=datetime.now(UTC))
        .returning(RadarAlert.id)
    )
    marked = len(result.all())
    await session.commit()
    return marked
