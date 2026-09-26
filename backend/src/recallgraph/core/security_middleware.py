"""Security middleware (pure ASGI): response headers, request body limit, auth rate limiting.

Settings are read from `app.state.settings` per request so limits can be changed in tests.
The rate limiter is in-process (per API instance); a multi-instance deployment needs a shared
store (documented in docs/SECURITY.md).
"""

import json
import math
import time
from collections.abc import Awaitable, Callable, MutableMapping
from typing import Any

from recallgraph.core.problems import PROBLEM_MEDIA_TYPE

Scope = MutableMapping[str, Any]
Message = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]

RATE_LIMITED_PATHS = frozenset(
    {"/api/v1/auth/login", "/api/v1/auth/register", "/api/v1/auth/refresh"}
)
_DOCS_PREFIXES = ("/docs", "/redoc", "/openapi.json")
_API_CSP = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"


def _settings(scope: Scope) -> Any:
    return scope["app"].state.settings


async def _problem(
    scope: Scope,
    send: Send,
    status: int,
    title: str,
    detail: str,
    headers: list[tuple[bytes, bytes]],
) -> None:
    body = json.dumps(
        {
            "type": "about:blank",
            "title": title,
            "status": status,
            "detail": detail,
            "instance": scope.get("path", ""),
            "request_id": scope.get("state", {}).get("request_id"),
        }
    ).encode()
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [
                (b"content-type", PROBLEM_MEDIA_TYPE.encode()),
                (b"content-length", str(len(body)).encode()),
                *headers,
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})


class SecurityHeadersMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path: str = scope.get("path", "")
        production = _settings(scope).environment in ("staging", "production")

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers += [
                    (b"x-content-type-options", b"nosniff"),
                    (b"x-frame-options", b"DENY"),
                    (b"referrer-policy", b"no-referrer"),
                    (b"cross-origin-opener-policy", b"same-origin"),
                ]
                if not path.startswith(_DOCS_PREFIXES):
                    headers.append((b"content-security-policy", _API_CSP.encode()))
                if path.startswith("/api/v1/auth"):
                    headers.append((b"cache-control", b"no-store"))
                if production:
                    headers.append(
                        (b"strict-transport-security", b"max-age=63072000; includeSubDomains")
                    )
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_with_headers)


class BodySizeLimitMiddleware:
    """Rejects bodies over `max_body_bytes` (declared or streamed) with 413."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        limit: int = _settings(scope).max_body_bytes
        for name, value in scope.get("headers", []):
            if name == b"content-length" and value.isdigit() and int(value) > limit:
                await _problem(
                    scope, send, 413, "Content Too Large", f"Body exceeds {limit} bytes.", []
                )
                return

        received = 0
        too_large = False

        async def limited_receive() -> Message:
            nonlocal received, too_large
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    too_large = True
                    return {"type": "http.disconnect"}
            return message

        started = False

        async def tracking_send(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        await self.app(scope, limited_receive, tracking_send)
        if too_large and not started:
            await _problem(
                scope, send, 413, "Content Too Large", f"Body exceeds {limit} bytes.", []
            )


class AuthRateLimitMiddleware:
    """Fixed-window limit per client IP and auth endpoint (brute force / credential stuffing)."""

    def __init__(self, app: ASGIApp, clock: Callable[[], float] = time.monotonic) -> None:
        self.app = app
        self.clock = clock
        self.windows: dict[tuple[str, str], tuple[float, int]] = {}

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        path: str = scope.get("path", "")
        if (
            scope["type"] != "http"
            or scope.get("method") != "POST"
            or path not in RATE_LIMITED_PATHS
        ):
            await self.app(scope, receive, send)
            return
        limit: int = _settings(scope).auth_rate_limit_per_minute
        client = scope.get("client")
        key = (client[0] if client else "unknown", path)
        now = self.clock()
        start, count = self.windows.get(key, (now, 0))
        if now - start >= 60:
            start, count = now, 0
        if count >= limit:
            retry_after = max(1, math.ceil(60 - (now - start)))
            await _problem(
                scope,
                send,
                429,
                "Too Many Requests",
                "Too many authentication attempts. Try again later.",
                [(b"retry-after", str(retry_after).encode())],
            )
            return
        self.windows[key] = (start, count + 1)
        if len(self.windows) > 50_000:  # bound memory: drop expired windows
            self.windows = {k: v for k, v in self.windows.items() if now - v[0] < 60}
        await self.app(scope, receive, send)
