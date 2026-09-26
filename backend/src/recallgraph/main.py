"""Application factory. Run: uvicorn recallgraph.main:create_app --factory"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from importlib.metadata import version

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from recallgraph.api.router import api_v1_router
from recallgraph.core.config import Settings, get_settings
from recallgraph.core.logging_config import configure_logging
from recallgraph.core.problems import register_exception_handlers
from recallgraph.core.request_context import RequestContextMiddleware
from recallgraph.core.security_middleware import (
    AuthRateLimitMiddleware,
    BodySizeLimitMiddleware,
    SecurityHeadersMiddleware,
)
from recallgraph.db.session import create_engine, create_session_factory


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    yield
    await app.state.engine.dispose()


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level, settings.log_json)

    public_docs = settings.environment not in ("staging", "production")
    app = FastAPI(
        title=settings.app_name,
        version=version("recallgraph"),
        lifespan=lifespan,
        docs_url="/docs" if public_docs else None,
        redoc_url="/redoc" if public_docs else None,
        openapi_url="/openapi.json" if public_docs else None,
    )
    app.state.settings = settings
    app.state.engine = create_engine(settings)
    app.state.session_factory = create_session_factory(app.state.engine)
    app.add_middleware(AuthRateLimitMiddleware)
    app.add_middleware(BodySizeLimitMiddleware)
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_methods=["GET", "POST", "PATCH", "DELETE"],
            allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
            allow_credentials=False,
            max_age=600,
        )
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RequestContextMiddleware)
    register_exception_handlers(app)
    app.include_router(api_v1_router)
    return app
