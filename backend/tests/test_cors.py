"""CORS: only the configured dev origins may read API responses from a browser."""

import httpx

from app.core.config import settings
from app.main import app

# A 404 path: answered without touching any database.
NO_DB_PATH = "/no-such-path"


async def request(method: str, path: str, headers: dict[str, str]) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as client:
        return await client.request(method, path, headers=headers)


async def test_preflight_from_the_dev_origin_is_allowed() -> None:
    r = await request(
        "OPTIONS",
        "/api/v1/projects",
        {
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert "POST" in r.headers["access-control-allow-methods"]


async def test_other_origins_get_no_cors_headers() -> None:
    r = await request(
        "OPTIONS",
        "/api/v1/projects",
        {"Origin": "https://evil.example", "Access-Control-Request-Method": "POST"},
    )
    assert r.status_code == 400
    assert "access-control-allow-origin" not in r.headers
    r = await request("GET", NO_DB_PATH, {"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in r.headers


async def test_simple_request_from_the_dev_origin_carries_the_header() -> None:
    r = await request("GET", NO_DB_PATH, {"Origin": "http://127.0.0.1:5173"})
    assert r.headers["access-control-allow-origin"] == "http://127.0.0.1:5173"


def test_no_wildcard_and_no_credentials() -> None:
    assert "*" not in settings.cors_allowed_origins
    cors = next(m for m in app.user_middleware if m.cls.__name__ == "CORSMiddleware")
    assert cors.kwargs["allow_credentials"] is False
