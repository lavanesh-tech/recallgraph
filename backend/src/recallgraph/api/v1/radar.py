"""Recall Radar notifications API (Bearer auth, per-user)."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from recallgraph.auth.dependencies import CurrentUser
from recallgraph.db.session import get_session
from recallgraph.radar.alerts import list_alerts, mark_all_read, mark_read, unread_count
from recallgraph.radar.schemas import AlertItemRef, AlertListResponse, AlertOut, MarkedResponse
from recallgraph.search.schemas import CompanyRef, RecallSummary

router = APIRouter(prefix="/radar", tags=["recall radar"])
SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.get("/alerts", response_model=AlertListResponse)
async def alerts(
    user: CurrentUser,
    session: SessionDep,
    unread_only: bool = False,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0, le=10_000)] = 0,
) -> AlertListResponse:
    total, views = await list_alerts(
        session, user.id, unread_only=unread_only, limit=limit, offset=offset
    )
    return AlertListResponse(
        items=[
            AlertOut(
                id=v.alert.id,
                tier=v.alert.tier,
                score=v.alert.score,
                engine_version=v.alert.engine_version,
                created_at=v.alert.created_at,
                read_at=v.alert.read_at,
                item=AlertItemRef(id=v.alert.inventory_item_id, nickname=v.item_nickname),
                recall=RecallSummary(
                    id=v.recall.id,
                    source=v.source,
                    source_record_id=v.recall.source_record_id,
                    recall_number=v.recall.recall_number,
                    title=v.recall.title,
                    recall_date=v.recall.recall_date,
                    url=v.recall.url,
                    companies=[CompanyRef(role=r, name=n) for r, n in v.companies],
                    score=v.alert.score,
                ),
            )
            for v in views
        ],
        total=total,
        unread=await unread_count(session, user.id),
        limit=limit,
        offset=offset,
    )


@router.post("/alerts/read-all", response_model=MarkedResponse)
async def read_all(user: CurrentUser, session: SessionDep) -> MarkedResponse:
    return MarkedResponse(marked=await mark_all_read(session, user.id))


@router.post("/alerts/{alert_id}/read", status_code=204)
async def read_one(alert_id: uuid.UUID, user: CurrentUser, session: SessionDep) -> Response:
    if not await mark_read(session, user.id, alert_id):
        raise HTTPException(status_code=404, detail="Alert not found.")
    return Response(status_code=204)
