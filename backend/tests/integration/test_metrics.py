"""Prometheus metrics through the real app."""

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.integration


async def test_metrics_use_route_templates_and_sample_outbox(client: AsyncClient) -> None:
    await client.get("/api/v1/health")
    await client.get("/api/v1/recalls/123456789")
    await client.get("/api/v1/recalls/987654321")

    response = await client.get("/metrics")
    body = response.text

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert 'route="/api/v1/recalls/{recall_id}",status="4xx"' in body
    assert "123456789" not in body  # raw ids never become label values
    assert 'recallgraph_outbox_events{status="pending"}' in body
    assert "recallgraph_http_request_duration_seconds_bucket" in body


async def test_metrics_endpoint_is_not_in_the_public_api_schema(client: AsyncClient) -> None:
    schema = (await client.get("/openapi.json")).json()
    assert "/metrics" not in schema["paths"]
