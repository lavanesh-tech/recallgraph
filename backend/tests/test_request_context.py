import pytest
from httpx import AsyncClient

from recallgraph.core.request_context import REQUEST_ID_HEADER


async def test_generates_request_id_when_absent(client: AsyncClient) -> None:
    response = await client.get("/api/v1/health")

    request_id = response.headers[REQUEST_ID_HEADER]
    assert len(request_id) == 32
    int(request_id, 16)  # uuid4().hex is valid hexadecimal


async def test_echoes_safe_caller_request_id(client: AsyncClient) -> None:
    response = await client.get("/api/v1/health", headers={REQUEST_ID_HEADER: "trace-abc.123_X"})

    assert response.headers[REQUEST_ID_HEADER] == "trace-abc.123_X"


@pytest.mark.parametrize("unsafe", ["has space", "<script>", "semi;colon", "x" * 65])
async def test_replaces_unsafe_caller_request_id(client: AsyncClient, unsafe: str) -> None:
    response = await client.get("/api/v1/health", headers={REQUEST_ID_HEADER: unsafe})

    returned = response.headers[REQUEST_ID_HEADER]
    assert returned != unsafe
    assert len(returned) == 32
