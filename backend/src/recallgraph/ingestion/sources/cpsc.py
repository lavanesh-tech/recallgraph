"""CPSC adapter: U.S. Consumer Product Safety Commission recalls (SaferProducts.gov REST API)."""

import asyncio
from dataclasses import dataclass
from datetime import date
from typing import Any

import httpx

from recallgraph.ingestion.http import FetchError, Sleep, get_json
from recallgraph.provenance.repository import RawRecordInput, SourceSpec

CPSC_RECALL_API_URL = "https://www.saferproducts.gov/RestWebServices/Recall"
CPSC_SOURCE = SourceSpec(
    code="cpsc",
    name="CPSC Recalls (SaferProducts.gov Recall REST API)",
    agency="U.S. Consumer Product Safety Commission",
    homepage_url="https://www.saferproducts.gov/",
)
EARLIEST_YEAR = 1970


@dataclass(frozen=True, slots=True)
class DateWindow:
    start: date
    end: date

    def params(self) -> dict[str, str]:
        return {
            "format": "json",
            "RecallDateStart": self.start.isoformat(),
            "RecallDateEnd": self.end.isoformat(),
        }

    def query_url(self) -> str:
        return str(httpx.URL(CPSC_RECALL_API_URL, params=self.params()))


def year_windows(from_year: int, to_year: int) -> list[DateWindow]:
    """One window per calendar year keeps each response small and each failure local."""
    if not EARLIEST_YEAR <= from_year <= to_year:
        raise ValueError(f"invalid year range {from_year}..{to_year}")
    return [DateWindow(date(y, 1, 1), date(y, 12, 31)) for y in range(from_year, to_year + 1)]


def to_raw_input(record: dict[str, Any], *, fallback_url: str) -> RawRecordInput:
    """Map one CPSC recall to a raw record. The payload is stored exactly as received."""
    recall_id = record.get("RecallID")
    if not isinstance(recall_id, int):
        raise ValueError(f"CPSC record without integer RecallID: {recall_id!r}")
    page_url = record.get("URL")
    source_url = page_url if isinstance(page_url, str) and page_url.startswith("http") else None
    return RawRecordInput(
        source_record_id=str(recall_id),
        payload=record,
        source_url=source_url or fallback_url,
    )


class CpscRecallClient:
    def __init__(
        self, http: httpx.AsyncClient, *, max_attempts: int = 4, sleep: Sleep = asyncio.sleep
    ) -> None:
        self._http = http
        self._max_attempts = max_attempts
        self._sleep = sleep

    async def fetch_window(self, window: DateWindow) -> list[dict[str, Any]]:
        data = await get_json(
            self._http,
            CPSC_RECALL_API_URL,
            params=window.params(),
            max_attempts=self._max_attempts,
            sleep=self._sleep,
        )
        if not isinstance(data, list) or not all(isinstance(item, dict) for item in data):
            raise FetchError("unexpected CPSC response shape (expected a JSON array of objects)")
        records: list[dict[str, Any]] = data
        return records
