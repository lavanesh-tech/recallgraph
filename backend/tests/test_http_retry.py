import httpx
import pytest

from recallgraph.ingestion.http import FetchError, get_json

URL = "https://example.invalid/api"


class Recorder:
    def __init__(self) -> None:
        self.delays: list[float] = []

    async def sleep(self, seconds: float) -> None:
        self.delays.append(seconds)


def _client(responses: list[httpx.Response | Exception]) -> tuple[httpx.AsyncClient, list[int]]:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        item = responses[min(len(calls), len(responses)) - 1]
        if isinstance(item, Exception):
            raise item
        return item

    return httpx.AsyncClient(transport=httpx.MockTransport(handler)), calls


async def test_retries_server_error_then_succeeds() -> None:
    client, calls = _client([httpx.Response(503), httpx.Response(200, json=[{"ok": 1}])])
    recorder = Recorder()

    data = await get_json(client, URL, params={}, sleep=recorder.sleep)

    assert data == [{"ok": 1}]
    assert len(calls) == 2
    assert len(recorder.delays) == 1


async def test_client_error_is_not_retried() -> None:
    client, calls = _client([httpx.Response(404)])

    with pytest.raises(FetchError, match="HTTP 404"):
        await get_json(client, URL, params={}, sleep=Recorder().sleep)
    assert len(calls) == 1


async def test_timeouts_exhaust_bounded_retries() -> None:
    client, calls = _client([httpx.ConnectTimeout("synthetic timeout")])

    with pytest.raises(FetchError, match="after 3 attempts"):
        await get_json(client, URL, params={}, max_attempts=3, sleep=Recorder().sleep)
    assert len(calls) == 3


async def test_retry_after_header_is_honored() -> None:
    client, _ = _client(
        [httpx.Response(429, headers={"Retry-After": "7"}), httpx.Response(200, json=[])]
    )
    recorder = Recorder()

    await get_json(client, URL, params={}, sleep=recorder.sleep)

    assert recorder.delays == [7.0]


async def test_invalid_json_is_an_error() -> None:
    client, _ = _client([httpx.Response(200, text="<html>not json</html>")])

    with pytest.raises(FetchError, match="invalid JSON"):
        await get_json(client, URL, params={}, sleep=Recorder().sleep)
