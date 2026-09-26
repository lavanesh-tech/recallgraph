"""Inventory persistence. Every query is scoped to the owning user (no cross-user access)."""

import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from recallgraph.inventory.models import InventoryItem
from recallgraph.matching.engine import MatchQuery

MAX_ITEMS_PER_USER = 200
PRODUCT_FIELDS = ("description", "manufacturer", "model", "upc")


class InventoryLimitError(Exception):
    pass


async def list_items(
    session: AsyncSession, user_id: uuid.UUID, limit: int, offset: int
) -> tuple[int, list[InventoryItem]]:
    owned = InventoryItem.user_id == user_id
    total: int = (
        await session.execute(select(func.count()).select_from(InventoryItem).where(owned))
    ).scalar_one()
    items = (
        await session.execute(
            select(InventoryItem)
            .where(owned)
            .order_by(InventoryItem.created_at.desc(), InventoryItem.id)
            .limit(limit)
            .offset(offset)
        )
    ).scalars()
    return total, list(items)


async def get_item(
    session: AsyncSession, user_id: uuid.UUID, item_id: uuid.UUID
) -> InventoryItem | None:
    """Returns None for items that do not exist AND for items owned by someone else."""
    return await session.scalar(
        select(InventoryItem).where(InventoryItem.id == item_id, InventoryItem.user_id == user_id)
    )


async def create_item(
    session: AsyncSession, user_id: uuid.UUID, fields: dict[str, Any]
) -> InventoryItem:
    count: int = (
        await session.execute(
            select(func.count()).select_from(InventoryItem).where(InventoryItem.user_id == user_id)
        )
    ).scalar_one()
    if count >= MAX_ITEMS_PER_USER:
        raise InventoryLimitError
    item = InventoryItem(user_id=user_id, **fields)
    session.add(item)
    await session.commit()
    await session.refresh(item)
    return item


def has_product_info(fields: dict[str, Any]) -> bool:
    return any(fields.get(name) for name in PRODUCT_FIELDS)


async def update_item(
    session: AsyncSession, item: InventoryItem, changes: dict[str, Any]
) -> InventoryItem:
    for name, value in changes.items():
        setattr(item, name, value)
    await session.commit()
    await session.refresh(item)
    return item


async def delete_item(session: AsyncSession, item: InventoryItem) -> None:
    await session.delete(item)
    await session.commit()


def to_match_query(item: InventoryItem) -> MatchQuery:
    return MatchQuery(
        description=item.description,
        manufacturer=item.manufacturer,
        model=item.model,
        upc=item.upc,
        category=item.category,
        purchase_year=item.purchase_year,
    )
