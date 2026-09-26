"""Resilient JSON-over-HTTP fetching: timeouts, bounded retries with backoff, explicit errors."""

import asyncio
import random
from collections.abc import Awaitable, Callable, Mapping
from typing import Any

import httpx
import structlog

logger = structlog.get_logger(__name__)

RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})
Sleep = Callable[[float], Awaitable[None]]


class FetchError(RuntimeError):
    """A request failed permanently or exhausted its retries."""


def _retry_after_seconds(response: httpx.Response, cap_s: float) -> float | None:
    value = response.headers.get("Retry-After", "")
    return min(float(value), cap_s) if value.isdigit() else None


async def get_json(
    client: httpx.AsyncClient,
    url: str,
    *,
    params: Mapping[str, str],
    max_attempts: int = 4,
    base_delay_s: float = 1.0,
    max_delay_s: float = 30.0,
    sleep: Sleep = asyncio.sleep,
) -> Any:
    """GET and decode JSON. Retries transport errors, 429 and 5xx; fails fast on other 4xx."""
    for attempt in range(1, max_attempts + 1):
        retry_after: float | None = None
        try:
            response = await client.get(url, params=params)
        except httpx.TransportError as exc:  # includes timeouts and connection errors
            reason = type(exc).__name__
        else:
            if response.status_code == httpx.codes.OK:
                try:
                    return response.json()
                except ValueError as exc:
                    raise FetchError(f"invalid JSON from {url}") from exc
            if response.status_code not in RETRYABLE_STATUS:
                raise FetchError(f"HTTP {response.status_code} from {url}")
            reason = f"HTTP {response.status_code}"
            retry_after = _retry_after_seconds(response, max_delay_s)

        if attempt == max_attempts:
            raise FetchError(f"{reason} from {url} after {max_attempts} attempts")
        backoff = min(max_delay_s, base_delay_s * 2 ** (attempt - 1))
        jitter = 0.5 + random.random() / 2  # noqa: S311 - jitter, not cryptography
        delay = retry_after if retry_after is not None else backoff * jitter
        logger.warning(
            "http_retry", url=url, attempt=attempt, reason=reason, delay_s=round(delay, 2)
        )
        await sleep(delay)
    raise AssertionError("unreachable")
