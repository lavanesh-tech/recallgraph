from typing import Any

from fastapi import FastAPI
from httpx import AsyncClient, Response
from recallgraph.core.problems import VALIDATION_PROBLEM_TYPE
from recallgraph.core.request_context import REQUEST_ID_HEADER


def assert_problem(response: Response, status: int, problem_type: str = "about:blank") -> Any:
    assert response.status_code == status
    assert response.headers["content-type"].startswith("application/problem+json")
    body = response.json()
    assert body["type"] == problem_type
    assert body["status"] == status
    assert isinstance(body["title"], str) and body["title"]
    assert body["instance"] == response.request.url.path
    assert body["request_id"] == response.headers[REQUEST_ID_HEADER]
    return body


async def test_unknown_route_returns_404_problem(client: AsyncClient) -> None:
    response = await client.get("/api/v1/does-not-exist")

    body = assert_problem(response, 404)
    assert body["title"] == "Not Found"


async def test_wrong_method_returns_405_problem_with_allow_header(client: AsyncClient) -> None:
    response = await client.post("/api/v1/health")

    assert_problem(response, 405)
    assert "GET" in response.headers["allow"]


async def test_validation_problem_does_not_echo_rejected_input(
    app: FastAPI, client: AsyncClient
) -> None:
    async def needs_int(limit: int) -> dict[str, int]:
        return {"limit": limit}

    app.add_api_route("/test/needs-int", needs_int)
    response = await client.get("/test/needs-int", params={"limit": "not-a-number"})

    body = assert_problem(response, 422, VALIDATION_PROBLEM_TYPE)
    assert body["errors"][0]["loc"] == ["query", "limit"]
    assert "not-a-number" not in response.text


async def test_unhandled_exception_returns_generic_500_problem(
    app: FastAPI, client: AsyncClient
) -> None:
    async def explode() -> None:
        raise RuntimeError("internal secret detail")

    app.add_api_route("/test/explode", explode)
    response = await client.get("/test/explode")

    body = assert_problem(response, 500)
    assert "detail" not in body
    assert "internal secret detail" not in response.text
