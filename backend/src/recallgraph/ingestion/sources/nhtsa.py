"""NHTSA adapter: vehicle/equipment/tire/child-seat recall campaigns.

Authoritative dataset: NHTSA "Recalls Data" published on data.transportation.gov (Socrata id
6axg-epim), paged with $limit/$offset in a stable nhtsa_id order.
"""

import asyncio
from collections.abc import AsyncIterator
from typing import Any

import httpx

from recallgraph.ingestion.base import Batch
from recallgraph.ingestion.http import FetchError, Sleep, get_json
from recallgraph.provenance.repository import RawRecordInput, SourceSpec

NHTSA_RECALLS_URL = "https://data.transportation.gov/resource/6axg-epim.json"
NHTSA_SOURCE = SourceSpec(
    code="nhtsa",
    name="NHTSA Recalls Data (data.transportation.gov dataset 6axg-epim)",
    agency="U.S. National Highway Traffic Safety Administration",
    homepage_url="https://www.nhtsa.gov/recalls",
)


def to_raw_input(record: dict[str, Any]) -> RawRecordInput:
    nhtsa_id = record.get("nhtsa_id")
    if not isinstance(nhtsa_id, str) or not nhtsa_id.strip():
        raise ValueError(f"NHTSA record without nhtsa_id: {nhtsa_id!r}")
    link = record.get("recall_link")
    url = link.get("url") if isinstance(link, dict) else None
    source_url = url if isinstance(url, str) and url.startswith("http") else None
    return RawRecordInput(
        source_record_id=nhtsa_id.strip(),
        payload=record,
        source_url=source_url or str(httpx.URL(NHTSA_RECALLS_URL, params={"nhtsa_id": nhtsa_id})),
    )


class NhtsaRecallClient:
    def __init__(
        self, http: httpx.AsyncClient, *, max_attempts: int = 4, sleep: Sleep = asyncio.sleep
    ) -> None:
        self._http = http
        self._max_attempts = max_attempts
        self._sleep = sleep

    async def fetch_page(self, offset: int, limit: int) -> list[dict[str, Any]]:
        data = await get_json(
            self._http,
            NHTSA_RECALLS_URL,
            params={"$limit": str(limit), "$offset": str(offset), "$order": "nhtsa_id"},
            max_attempts=self._max_attempts,
            sleep=self._sleep,
        )
        if not isinstance(data, list) or not all(isinstance(item, dict) for item in data):
            raise FetchError("unexpected NHTSA response shape (expected a JSON array of objects)")
        records: list[dict[str, Any]] = data
        return records


class NhtsaAdapter:
    """SourceAdapter paging through the whole dataset until a short page is returned."""

    def __init__(
        self,
        client: NhtsaRecallClient,
        *,
        page_size: int = 5000,
        max_pages: int | None = None,
        pause_s: float = 0.5,
        sleep: Sleep = asyncio.sleep,
    ) -> None:
        if page_size < 1:
            raise ValueError("page_size must be positive")
        self.spec = NHTSA_SOURCE
        self._client = client
        self._page_size = page_size
        self._max_pages = max_pages
        self._pause_s = pause_s
        self._sleep = sleep

    def parameters(self) -> dict[str, Any]:
        return {
            "api": NHTSA_RECALLS_URL,
            "order": "nhtsa_id",
            "page_size": self._page_size,
            "max_pages": self._max_pages,
        }

    async def batches(self) -> AsyncIterator[Batch]:
        page = 0
        while self._max_pages is None or page < self._max_pages:
            if page:
                await self._sleep(self._pause_s)
            offset = page * self._page_size
            records = await self._client.fetch_page(offset, self._page_size)
            if records:
                yield Batch(label=f"offset={offset}", records=[to_raw_input(r) for r in records])
            if len(records) < self._page_size:
                return
            page += 1
