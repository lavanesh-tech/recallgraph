"""RFC 9457 problem details (application/problem+json) for every error response."""

from collections.abc import Mapping
from http import HTTPStatus
from typing import Any

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from recallgraph.core.request_context import REQUEST_ID_HEADER

PROBLEM_MEDIA_TYPE = "application/problem+json"
VALIDATION_PROBLEM_TYPE = "urn:recallgraph:problem:validation-error"

logger = structlog.get_logger(__name__)


def _request_id(request: Request) -> str | None:
    value = getattr(request.state, "request_id", None)
    return value if isinstance(value, str) else None


def problem_response(
    request: Request,
    status: int,
    *,
    detail: str | None = None,
    problem_type: str = "about:blank",
    title: str | None = None,
    extensions: Mapping[str, Any] | None = None,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    body: dict[str, Any] = {
        "type": problem_type,
        "title": title or HTTPStatus(status).phrase,
        "status": status,
        "instance": request.url.path,
        "request_id": _request_id(request),
    }
    if detail is not None:
        body["detail"] = detail
    if extensions:
        body.update(extensions)
    return JSONResponse(
        status_code=status, content=body, headers=headers, media_type=PROBLEM_MEDIA_TYPE
    )


async def _handle_http_exception(request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, StarletteHTTPException):
        raise exc
    phrase = HTTPStatus(exc.status_code).phrase
    detail = str(exc.detail) if str(exc.detail) != phrase else None
    return problem_response(request, exc.status_code, detail=detail, headers=exc.headers)


async def _handle_validation_error(request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, RequestValidationError):
        raise exc
    # Location/message/type only: the rejected input is never echoed back.
    errors = [
        {
            "loc": list(err.get("loc", ())),
            "msg": err.get("msg", ""),
            "type": err.get("type", ""),
        }
        for err in exc.errors()
    ]
    return problem_response(
        request,
        422,
        problem_type=VALIDATION_PROBLEM_TYPE,
        title="Request validation failed",
        detail="One or more request parameters are invalid.",
        extensions={"errors": errors},
    )


async def _handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
    request_id = _request_id(request)
    logger.error("unhandled_exception", request_id=request_id, path=request.url.path, exc_info=exc)
    response = problem_response(request, 500)
    if request_id is not None:
        # This response bypasses the middleware, so set the correlation header here.
        response.headers[REQUEST_ID_HEADER] = request_id
    return response


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(StarletteHTTPException, _handle_http_exception)
    app.add_exception_handler(RequestValidationError, _handle_validation_error)
    app.add_exception_handler(Exception, _handle_unexpected)
