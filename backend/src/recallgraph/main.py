"""Application factory. Run: uvicorn recallgraph.main:create_app --factory"""

from importlib.metadata import version

from fastapi import FastAPI

from recallgraph.api.router import api_v1_router
from recallgraph.core.config import Settings, get_settings
from recallgraph.core.logging_config import configure_logging
from recallgraph.core.problems import register_exception_handlers
from recallgraph.core.request_context import RequestContextMiddleware


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level, settings.log_json)

    app = FastAPI(title=settings.app_name, version=version("recallgraph"))
    app.state.settings = settings
    app.add_middleware(RequestContextMiddleware)
    register_exception_handlers(app)
    app.include_router(api_v1_router)
    return app
