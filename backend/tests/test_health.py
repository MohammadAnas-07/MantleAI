import time

import httpx

from app.main import app


async def test_health_returns_ok() -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as client:
        start = time.perf_counter()
        response = await client.get("/health")
        elapsed = time.perf_counter() - start

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"] in {"up", "down"}
    # Must answer fast even when Postgres is not running.
    assert elapsed < 3, f"/health took {elapsed:.2f}s"
