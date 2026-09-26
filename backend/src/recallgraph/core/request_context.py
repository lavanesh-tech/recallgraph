"""Per-request correlation ID and request-completion logging."""

import re
import time
import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

REQUEST_ID_HEADER = "X-Request-ID"
_SAFE_REQUEST_ID = re.compile(r"[A-Za-z0-9._-]{1,64}")

logger = structlog.get_logger(__name__)


def resolve_request_id(incoming: str | None) -> str:
    """Reuse a caller-supplied ID only if it is safe to log and echo; otherwise mint one."""
    if incoming is not None and _SAFE_REQUEST_ID.fullmatch(incoming):
        return incoming
    return uuid.uuid4().hex


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = resolve_request_id(request.headers.get(REQUEST_ID_HEADER))
        request.state.request_id = request_id
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)
        started = time.perf_counter()

        response = await call_next(request)

        response.headers[REQUEST_ID_HEADER] = request_id
        # Path only: query strings may carry user data and are not logged.
        logger.info(
            "request_completed",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=round((time.perf_counter() - started) * 1000, 2),
        )
        return response
