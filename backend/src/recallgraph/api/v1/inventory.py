"""Saved-inventory endpoints. All require a bearer token and are scoped to the caller.
Items owned by other users are indistinguishable from missing ones (404, never 403)."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from recallgraph.api.v1.match import build_match_response
from recallgraph.auth.dependencies import CurrentUser
from recallgraph.db.session import get_session
from recallgraph.inventory.models import InventoryItem
from recallgraph.inventory.schemas import (
    InventoryItemIn,
    InventoryItemOut,
    InventoryItemUpdate,
    InventoryListResponse,
)
from recallgraph.inventory.service import (
    InventoryLimitError,
    create_item,
    delete_item,
    get_item,
    has_product_info,
    list_items,
    to_match_query,
    update_item,
)
from recallgraph.matching.schemas import MatchResponse
from recallgraph.matching.service import match_product

router = APIRouter(prefix="/inventory", tags=["inventory"])
SessionDep = Annotated[AsyncSession, Depends(get_session)]


def _out(item: InventoryItem) -> InventoryItemOut:
    return InventoryItemOut(
        id=item.id,
        nickname=item.nickname,
        description=item.description,
        manufacturer=item.manufacturer,
        model=item.model,
        upc=item.upc,
        category=item.category,
        purchase_year=item.purchase_year,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


async def _owned(session: AsyncSession, user: CurrentUser, item_id: uuid.UUID) -> InventoryItem:
    item = await get_item(session, user.id, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Inventory item not found.")
    return item


@router.post("", status_code=201, response_model=InventoryItemOut)
async def create(body: InventoryItemIn, user: CurrentUser, session: SessionDep) -> InventoryItemOut:
    try:
        item = await create_item(session, user.id, body.model_dump())
    except InventoryLimitError as exc:
        raise HTTPException(status_code=409, detail="Inventory item limit reached.") from exc
    return _out(item)


@router.get("", response_model=InventoryListResponse)
async def list_inventory(
    user: CurrentUser,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0, le=10_000)] = 0,
) -> InventoryListResponse:
    total, items = await list_items(session, user.id, limit, offset)
    return InventoryListResponse(
        items=[_out(i) for i in items], total=total, limit=limit, offset=offset
    )


@router.get("/{item_id}", response_model=InventoryItemOut)
async def read(item_id: uuid.UUID, user: CurrentUser, session: SessionDep) -> InventoryItemOut:
    return _out(await _owned(session, user, item_id))


@router.patch("/{item_id}", response_model=InventoryItemOut)
async def update(
    item_id: uuid.UUID, body: InventoryItemUpdate, user: CurrentUser, session: SessionDep
) -> InventoryItemOut:
    item = await _owned(session, user, item_id)
    changes = body.model_dump(exclude_unset=True)
    if "nickname" in changes and changes["nickname"] is None:
        raise HTTPException(status_code=422, detail="nickname cannot be null.")
    merged = {name: getattr(item, name) for name in InventoryItemOut.model_fields} | changes
    if not has_product_info(merged):
        raise HTTPException(
            status_code=422,
            detail="An item needs at least one of description, manufacturer, model or upc.",
        )
    return _out(await update_item(session, item, changes))


@router.delete("/{item_id}", status_code=204)
async def delete(item_id: uuid.UUID, user: CurrentUser, session: SessionDep) -> Response:
    await delete_item(session, await _owned(session, user, item_id))
    return Response(status_code=204)


@router.get("/{item_id}/matches", response_model=MatchResponse)
async def matches(
    item_id: uuid.UUID,
    user: CurrentUser,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
) -> MatchResponse:
    item = await _owned(session, user, item_id)
    return build_match_response(await match_product(session, to_match_query(item), limit))
