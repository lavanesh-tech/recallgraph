from httpx import ASGITransport, AsyncClient

from recallgraph.core.config import Settings
from recallgraph.main import create_app


async def test_ready_returns_503_problem_when_database_unreachable() -> None:
    settings = Settings(
        environment="test",
        log_level="ERROR",
        # Port 1 on localhost: guaranteed connection refusal, no real DB needed.
        database_url="postgresql+asyncpg://recallgraph:s3cret-pw@127.0.0.1:1/none",
        db_readiness_timeout_s=2.0,
    )
    app = create_app(settings)
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    try:
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.get("/api/v1/ready")
    finally:
        await app.state.engine.dispose()

    assert response.status_code == 503
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["checks"] == {"database": "unavailable"}
    assert "s3cret-pw" not in response.text
