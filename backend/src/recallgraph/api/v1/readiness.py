"""Readiness endpoint: is this instance able to serve traffic (database reachable)?"""

import asyncio
from typing import Literal

import structlog
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from recallgraph.core.config import Settings
from recallgraph.core.problems import problem_response

router = APIRouter(tags=["health"])
logger = structlog.get_logger(__name__)


class ReadinessChecks(BaseModel):
    database: Literal["ok"]


class ReadinessResponse(BaseModel):
    status: Literal["ready"]
    checks: ReadinessChecks


async def _database_reachable(engine: AsyncEngine, timeout_s: float) -> bool:
    try:
        async with asyncio.timeout(timeout_s), engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
    # A readiness probe must report failure, never raise: any error means "not ready".
    except Exception as exc:
        logger.warning("readiness_database_unavailable", error_type=type(exc).__name__)
        return False
    return True


@router.get(
    "/ready",
    response_model=ReadinessResponse,
    responses={503: {"description": "Not ready (RFC 9457 problem details)"}},
)
async def ready(request: Request) -> ReadinessResponse | JSONResponse:
    settings: Settings = request.app.state.settings
    if await _database_reachable(request.app.state.engine, settings.db_readiness_timeout_s):
        return ReadinessResponse(status="ready", checks=ReadinessChecks(database="ok"))
    return problem_response(
        request,
        503,
        detail="Database is unavailable.",
        extensions={"checks": {"database": "unavailable"}},
    )
