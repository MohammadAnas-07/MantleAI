"""The Host header check: only localhost and 127.0.0.1 are served (DNS rebinding defence)."""

import httpx
import pytest

from app.api.errors import host_allowed
from app.main import app

NO_DB_PATH = "/no-such-path"  # answered without touching any database


async def get(host: str, path: str = NO_DB_PATH) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as client:
        return await client.get(path, headers={"Host": host})


@pytest.mark.parametrize(
    "host", ["localhost", "localhost:8000", "127.0.0.1", "127.0.0.1:8001", "LOCALHOST:8000"]
)
async def test_local_hosts_are_served(host: str) -> None:
    r = await get(host)
    assert r.status_code == 404  # reached the app; the path just doesn't exist


async def test_dns_rebinding_request_is_refused() -> None:
    # A page on attacker.example whose DNS name now points at 127.0.0.1: the browser connects
    # to our port but still sends the attacker's host name.
    r = await get("attacker.example:8000", "/api/v1/credentials")
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "invalid_host"


@pytest.mark.parametrize("host", ["", "localhost.attacker.example", "127.0.0.1.nip.io", "0.0.0.0"])
async def test_lookalike_and_missing_hosts_are_refused(host: str) -> None:
    assert (await get(host)).status_code == 400


def test_matching_rules() -> None:
    allowed = ["localhost", "127.0.0.1", "[::1]", "mantle.test:9000"]
    assert host_allowed("[::1]:8000", allowed)
    assert host_allowed("mantle.test:9000", allowed)
    assert not host_allowed("mantle.test:9001", allowed)
    assert not host_allowed("mantle.test", allowed)
