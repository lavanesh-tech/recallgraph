"""Liveness endpoint. A database-aware readiness check arrives with the DB layer."""

from typing import Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel

from recallgraph.core.config import Settings

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: str
    version: str
    environment: str


@router.get("/health", response_model=HealthResponse)
async def health(request: Request) -> HealthResponse:
    settings: Settings = request.app.state.settings
    return HealthResponse(
        status="ok",
        service=settings.app_name,
        version=request.app.version,
        environment=settings.environment,
    )
