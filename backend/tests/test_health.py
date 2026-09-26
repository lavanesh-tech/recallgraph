from importlib.metadata import version

from httpx import AsyncClient


async def test_health_returns_service_metadata(client: AsyncClient) -> None:
    response = await client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "RecallGraph",
        "version": version("recallgraph"),
        "environment": "test",
    }
