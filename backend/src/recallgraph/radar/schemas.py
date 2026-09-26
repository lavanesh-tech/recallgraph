"""Radar alert response models."""

import uuid
from datetime import datetime

from pydantic import BaseModel

from recallgraph.matching.schemas import MATCH_DISCLAIMER
from recallgraph.search.schemas import RecallSummary


class AlertItemRef(BaseModel):
    id: uuid.UUID
    nickname: str


class AlertOut(BaseModel):
    id: uuid.UUID
    tier: str
    score: float
    engine_version: str
    created_at: datetime
    read_at: datetime | None
    item: AlertItemRef
    recall: RecallSummary


class AlertListResponse(BaseModel):
    items: list[AlertOut]
    total: int
    unread: int
    limit: int
    offset: int
    disclaimer: str = MATCH_DISCLAIMER


class MarkedResponse(BaseModel):
    marked: int
