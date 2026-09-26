"""NHTSA adapter unit tests. All records are SYNTHETIC, shaped like the real dataset."""

from typing import Any

import httpx
import pytest

from recallgraph.ingestion.sources.nhtsa import NhtsaAdapter, NhtsaRecallClient, to_raw_input


def _record(i: int) -> dict[str, Any]:
    return {
        "nhtsa_id": f"99V{i:06d}",
        "subject": f"SYNTHETIC recall {i}",
        "recall_link": {"url": f"https://example.invalid/{i}", "description": "Go to Recall"},
    }


async def _no_sleep(_: float) -> None:
    return None


async def test_pages_until_a_short_page_with_stable_order() -> None:
    requests: list[dict[str, str]] = []
    data = [_record(i) for i in range(5)]

    def handler(request: httpx.Request) -> httpx.Response:
        params = dict(request.url.params)
        requests.append(params)
        offset, limit = int(params["$offset"]), int(params["$limit"])
        return httpx.Response(200, json=data[offset : offset + limit])

    client = NhtsaRecallClient(httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    adapter = NhtsaAdapter(client, page_size=2, sleep=_no_sleep)

    batches = [b async for b in adapter.batches()]

    assert [len(b.records) for b in batches] == [2, 2, 1]
    assert [r["$offset"] for r in requests] == ["0", "2", "4"]
    assert all(r["$order"] == "nhtsa_id" for r in requests)


async def test_max_pages_bounds_the_run() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[_record(1), _record(2)])

    client = NhtsaRecallClient(httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    adapter = NhtsaAdapter(client, page_size=2, max_pages=3, sleep=_no_sleep)

    assert len([b async for b in adapter.batches()]) == 3


def test_to_raw_input_requires_nhtsa_id() -> None:
    with pytest.raises(ValueError, match="nhtsa_id"):
        to_raw_input({"subject": "x"})


def test_to_raw_input_falls_back_to_dataset_query_url() -> None:
    raw = to_raw_input({"nhtsa_id": "26V000001"})

    assert raw.source_record_id == "26V000001"
    assert raw.source_url.startswith("https://data.transportation.gov/resource/6axg-epim.json")
