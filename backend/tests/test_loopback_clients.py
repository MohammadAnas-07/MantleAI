"""Only clients on this computer may call the API (audit A-018), unless ALLOW_REMOTE_CLIENTS is
set. The Host check alone doesn't stop a LAN client that sends `Host: localhost` when someone
starts uvicorn with --host 0.0.0.0. No database: /openapi.json needs none."""

import logging

import httpx
import pytest

from app.api.errors import client_is_loopback
from app.core.config import settings
from app.main import app, log_client_policy


async def get_from(client: tuple[str, int]) -> httpx.Response:
    transport = httpx.ASGITransport(app=app, client=client)
    async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as c:
        return await c.get("/openapi.json")


@pytest.mark.parametrize("host", ["127.0.0.1", "127.5.0.1", "::1", "::ffff:127.0.0.1"])
async def test_loopback_clients_are_served(host: str) -> None:
    assert (await get_from((host, 50000))).status_code == 200


@pytest.mark.parametrize("host", ["192.168.1.20", "10.0.0.5", "fe80::1", "8.8.8.8", "testclient"])
async def test_other_clients_get_403(host: str) -> None:
    r = await get_from((host, 50000))
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "remote_client_refused"
    assert host not in r.text


async def test_the_setting_lets_other_clients_in(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "allow_remote_clients", True)
    assert (await get_from(("192.168.1.20", 50000))).status_code == 200


def test_a_unix_socket_has_no_address_and_is_local() -> None:
    assert client_is_loopback(None)


def test_startup_says_which_policy_is_on(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger="app.main")
    log_client_policy()
    assert "only from this computer" in caplog.text
    caplog.clear()
    monkeypatch.setattr(settings, "allow_remote_clients", True)
    log_client_policy()
    record = caplog.records[-1]
    assert record.levelno == logging.WARNING and "ALLOW_REMOTE_CLIENTS" in record.getMessage()
