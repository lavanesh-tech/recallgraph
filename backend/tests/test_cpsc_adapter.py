"""CPSC adapter unit tests. All records here are SYNTHETIC, shaped like the real API."""

from datetime import date

import httpx
import pytest

from recallgraph.ingestion.http import FetchError
from recallgraph.ingestion.sources.cpsc import (
    CpscRecallClient,
    DateWindow,
    to_raw_input,
    year_windows,
)


def test_year_windows_cover_whole_calendar_years() -> None:
    assert year_windows(2024, 2025) == [
        DateWindow(date(2024, 1, 1), date(2024, 12, 31)),
        DateWindow(date(2025, 1, 1), date(2025, 12, 31)),
    ]


@pytest.mark.parametrize(("start", "end"), [(2025, 2024), (1900, 2000)])
def test_year_windows_reject_invalid_ranges(start: int, end: int) -> None:
    with pytest.raises(ValueError):
        year_windows(start, end)


def test_to_raw_input_keeps_payload_and_uses_recall_page_url() -> None:
    record = {"RecallID": 123, "URL": "https://www.cpsc.gov/Recalls/synthetic", "Title": "X"}

    raw = to_raw_input(record, fallback_url="https://fallback.invalid")

    assert raw.source_record_id == "123"
    assert raw.payload is record
    assert raw.source_url == "https://www.cpsc.gov/Recalls/synthetic"


def test_to_raw_input_falls_back_to_query_url() -> None:
    raw = to_raw_input({"RecallID": 5, "URL": ""}, fallback_url="https://fallback.invalid/q")

    assert raw.source_url == "https://fallback.invalid/q"


def test_record_without_recall_id_is_rejected() -> None:
    with pytest.raises(ValueError, match="RecallID"):
        to_raw_input({"Title": "no id"}, fallback_url="https://fallback.invalid")


async def test_fetch_window_sends_date_params_and_validates_shape() -> None:
    seen_params: list[dict[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_params.append(dict(request.url.params))
        return httpx.Response(200, json={"not": "a list"})

    client = CpscRecallClient(httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    window = DateWindow(date(2024, 1, 1), date(2024, 12, 31))

    with pytest.raises(FetchError, match="unexpected CPSC response shape"):
        await client.fetch_window(window)
    assert seen_params == [
        {"format": "json", "RecallDateStart": "2024-01-01", "RecallDateEnd": "2024-12-31"}
    ]
