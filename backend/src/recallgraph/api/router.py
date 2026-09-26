"""Versioned API router. All public endpoints live under /api/v1."""

from fastapi import APIRouter

from recallgraph.api.v1 import auth, health, history, inventory, match, readiness, recalls

api_v1_router = APIRouter(prefix="/api/v1")
api_v1_router.include_router(health.router)
api_v1_router.include_router(readiness.router)
api_v1_router.include_router(auth.router)
# Static "/recalls/timeline" must be registered before "/recalls/{recall_id}".
api_v1_router.include_router(history.timeline_router)
api_v1_router.include_router(recalls.router)
api_v1_router.include_router(history.companies_router)
api_v1_router.include_router(match.router)
api_v1_router.include_router(inventory.router)
