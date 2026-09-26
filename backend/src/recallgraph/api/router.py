"""Versioned API router. All public endpoints live under /api/v1."""

from fastapi import APIRouter

from recallgraph.api.v1 import health, readiness

api_v1_router = APIRouter(prefix="/api/v1")
api_v1_router.include_router(health.router)
api_v1_router.include_router(readiness.router)
