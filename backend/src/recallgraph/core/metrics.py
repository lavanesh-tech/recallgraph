"""Prometheus metrics. Labels use route templates (never raw paths) to bound cardinality.

`/metrics` is served at the app root, outside `/api`, so the public web proxy never exposes it;
Prometheus scrapes the API container directly on the internal network.
"""

import time
from collections.abc import Awaitable, Callable, MutableMapping
from typing import Any

from fastapi import FastAPI, Request, Response
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)
from sqlalchemy import text

Scope = MutableMapping[str, Any]
Message = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]

REGISTRY = CollectorRegistry(auto_describe=True)

HTTP_REQUESTS = Counter(
    "recallgraph_http_requests_total",
    "HTTP requests by method, route template and status class.",
    ["method", "route", "status"],
    registry=REGISTRY,
)
HTTP_LATENCY = Histogram(
    "recallgraph_http_request_duration_seconds",
    "HTTP request latency by route template.",
    ["method", "route"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
    registry=REGISTRY,
)
EXPLANATIONS = Counter(
    "recallgraph_explanations_total",
    "Explanations by mode (llm or template fallback).",
    ["mode"],
    registry=REGISTRY,
)
OUTBOX_EVENTS = Gauge(
    "recallgraph_outbox_events",
    "Outbox events by status (sampled at scrape time).",
    ["status"],
    registry=REGISTRY,
)
OUTBOX_OLDEST_PENDING = Gauge(
    "recallgraph_outbox_oldest_pending_age_seconds",
    "Age of the oldest pending outbox event (0 when none).",
    registry=REGISTRY,
)
_OUTBOX_STATUSES = ("pending", "sent", "dead")


def _route_template(scope: Scope) -> str:
    """Full path with path-parameter values replaced by their names: /api/v1/recalls/{recall_id}."""
    if scope.get("route") is None:
        return "unmatched"
    path: str = scope.get("path", "")
    segments = path.split("/")
    for name, value in (scope.get("path_params") or {}).items():
        segments = [f"{{{name}}}" if seg == str(value) else seg for seg in segments]
    return "/".join(segments)


class MetricsMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("path") == "/metrics":
            await self.app(scope, receive, send)
            return
        status = 500
        started = time.perf_counter()

        async def capture(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = int(message["status"])
            await send(message)

        try:
            await self.app(scope, receive, capture)
        finally:
            route = _route_template(scope)
            method = scope.get("method", "GET")
            HTTP_REQUESTS.labels(method, route, f"{status // 100}xx").inc()
            HTTP_LATENCY.labels(method, route).observe(time.perf_counter() - started)


async def _sample_outbox(request: Request) -> None:
    try:
        async with request.app.state.session_factory() as session:
            rows = (
                await session.execute(
                    text("SELECT status, count(*) FROM outbox_events GROUP BY status")
                )
            ).all()
            oldest = (
                await session.execute(
                    text(
                        "SELECT coalesce(extract(epoch FROM now() - min(created_at)), 0) "
                        "FROM outbox_events WHERE status = 'pending'"
                    )
                )
            ).scalar_one()
    except Exception:  # metrics must never fail because the database is down
        return
    counts = {status: 0 for status in _OUTBOX_STATUSES} | {str(s): int(c) for s, c in rows}
    for status, count in counts.items():
        OUTBOX_EVENTS.labels(status).set(count)
    OUTBOX_OLDEST_PENDING.set(float(oldest or 0))


def register_metrics(app: FastAPI) -> None:
    async def metrics(request: Request) -> Response:
        await _sample_outbox(request)
        return Response(generate_latest(REGISTRY), media_type=CONTENT_TYPE_LATEST)

    app.add_api_route("/metrics", metrics, methods=["GET"], include_in_schema=False)
