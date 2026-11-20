"""Provider keys saved with one MASTER_ENCRYPTION_KEY, read with another (audit A-004).

Each feature must say clearly that the saved key can't be decrypted, with what to do, and
never answer with a bare 500 (which the browser shows as "API unreachable"). The stored
ciphertext is never changed or deleted, and no key or ciphertext appears in a response or log.
"""

import logging
import uuid
from pathlib import Path
from typing import Any

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.models import User
from app.modules.conversations.repository import MessageRepository
from app.modules.llm.fake import FakeProvider
from app.modules.llm.gateway import Gateway
from app.modules.llm.models import ProviderCredential
from tests.api_helpers import api_client, parse_sse
from tests.conversation_helpers import World, make_world

pytestmark = pytest.mark.db

CODE = "credential_unreadable"


@pytest.fixture
async def world(session: AsyncSession) -> World:
    """Keys saved with the test's master key ("key A"). /health looks at the default local
    user's keys, so this user is made the only default one (rolled back after the test)."""
    world = await make_world(session)
    await session.execute(update(User).values(is_local_default=User.id == world.user_id))
    await session.flush()
    return world


@pytest.fixture
def key_b(monkeypatch: pytest.MonkeyPatch) -> str:
    """Restart with another master key: every saved provider key is now unreadable."""
    other = Fernet.generate_key().decode()
    monkeypatch.setattr(settings, "master_encryption_key", other)
    return other


async def ciphertexts(session: AsyncSession, world: World) -> dict[str, bytes]:
    rows = await session.scalars(
        select(ProviderCredential).where(ProviderCredential.user_id == world.user_id)
    )
    return {str(r.id): bytes(r.encrypted_key) for r in rows}


def assert_clear(error: dict[str, Any]) -> None:
    assert error["code"] == CODE
    assert "MASTER_ENCRYPTION_KEY" in error["message"]
    assert "enter" in error["message"].lower()  # what to do: restore it, or enter the key again


async def test_chat_reports_an_unreadable_key_as_an_error_event(
    session: AsyncSession, world: World, key_b: str, caplog: pytest.LogCaptureFixture
) -> None:
    before = await ciphertexts(session, world)
    caplog.set_level(logging.DEBUG)
    async with api_client(session, Gateway(FakeProvider()), world.user_id) as client:
        r = await client.post(
            f"/api/v1/conversations/{world.conversation_id}/messages", json={"content": "Hi"}
        )
    assert r.status_code == 200
    events = parse_sse(r.text)
    assert [name for name, _ in events][-1] == "error"
    assert_clear(events[-1][1])
    [_, reply] = await MessageRepository(session, world.user_id).in_order(world.conversation_id)
    assert (reply.status, reply.error_code) == ("error", CODE)  # not "cancelled"
    assert await ciphertexts(session, world) == before  # never touched
    assert key_b not in caplog.text and "sk-test-" not in caplog.text


async def test_key_test_reports_an_unreadable_key(
    session: AsyncSession, world: World, key_b: str
) -> None:
    [credential_id] = list(await ciphertexts(session, world))[:1]
    async with api_client(session, Gateway(FakeProvider()), world.user_id) as client:
        r = await client.post(f"/api/v1/credentials/{credential_id}/test", json={})
        listed = (await client.get("/api/v1/credentials")).json()
    assert r.status_code == 200 and r.json()["ok"] is False
    assert r.json()["error_code"] == CODE
    assert listed and all(c["readable"] is False for c in listed)
    for text in (r.text, str(listed)):
        assert "sk-test-" not in text and "gAAAA" not in text  # no key, no Fernet token


async def test_a_new_key_replaces_the_unreadable_one_through_the_normal_save(
    session: AsyncSession, world: World, key_b: str
) -> None:
    before = await ciphertexts(session, world)
    async with api_client(session, Gateway(FakeProvider()), world.user_id) as client:
        saved = await client.post(
            "/api/v1/credentials",
            json={"provider": "openai", "label": "again", "api_key": "sk-test-again-00000000"},
        )
        listed = {c["id"]: c["readable"] for c in (await client.get("/api/v1/credentials")).json()}
    assert saved.status_code in (200, 201), saved.text
    assert listed[saved.json()["id"]] is True
    after = await ciphertexts(session, world)
    assert {k: v for k, v in after.items() if k in before} == before  # old rows untouched


async def test_health_reports_unreadable_keys(
    session: AsyncSession, world: World, key_b: str
) -> None:
    async with api_client(session, Gateway(FakeProvider()), world.user_id) as client:
        body = (await client.get("/health")).json()
    assert body["keys"] == "unreadable"
    assert set(body) == {"status", "database", "keys"}  # a status only, nothing more


async def test_health_reports_readable_keys(session: AsyncSession, world: World) -> None:
    async with api_client(session, Gateway(FakeProvider()), world.user_id) as client:
        assert (await client.get("/health")).json()["keys"] == "ok"


async def test_an_unexpected_error_still_answers_in_the_error_shape_with_cors(
    session: AsyncSession, world: World, monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:  # fmt: skip
    """A bug anywhere must not look like "API unreachable": 500 in our error shape, CORS
    headers kept, and only the exception type in the log."""
    from app.modules.conversations import router

    marker = "zebra-" + "marker-in-an-exception"

    async def broken(*_: object, **__: object) -> None:
        raise RuntimeError(marker)

    monkeypatch.setattr(router.service, "list_conversations", broken)
    caplog.set_level(logging.DEBUG)
    async with api_client(session, Gateway(FakeProvider()), world.user_id) as client:
        r = await client.get(
            f"/api/v1/projects/{world.project_id}/conversations",
            headers={"Origin": "http://localhost:5173"},
        )
    assert r.status_code == 500
    assert r.json()["error"]["code"] == "internal_error"
    assert r.headers.get("access-control-allow-origin") == "http://localhost:5173"
    assert marker not in r.text and marker not in caplog.text
    assert "RuntimeError" in caplog.text


async def test_runs_store_the_code_and_our_message(
    session: AsyncSession, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, key_b: str
) -> None:
    """Agent, gap finder and index runs after a master-key change fail with the code and our
    message, not exception text. The worlds save their keys with `key_b`; then the master key
    changes once more."""
    from app.modules.workflow.models import AgentRun
    from tests.agent_helpers import make_agent_world, plan, review
    from tests.rag_helpers import copy_fixture, fast_settings, index_once, make_rag_world

    fast_settings(monkeypatch)
    agents = await make_agent_world(session)
    rag = await make_rag_world(session, copy_fixture(tmp_path))
    monkeypatch.setattr(settings, "master_encryption_key", Fernet.generate_key().decode())

    agents.script.say("planner", plan())
    agents.script.say("reviewer", review())
    async with api_client(session, agents.gateway, agents.user_id) as client:
        r = await client.post(f"/api/v1/projects/{agents.project_id}/agent-runs", json={
            "run_type": "review", "model_id": str(agents.model_id)})  # fmt: skip
        assert r.status_code == 202, r.text
        run = await session.get(AgentRun, uuid.UUID(r.json()["id"]))
        assert run is not None
        await session.refresh(run)
        assert (run.status, run.error) == ("failed", CODE)
        assert run.error_message is not None and "MASTER_ENCRYPTION_KEY" in run.error_message

        gap = await client.post(f"/api/v1/projects/{agents.project_id}/gap-finder",
                                json={"model_id": str(agents.model_id)})  # fmt: skip
        assert gap.status_code == 422 and gap.json()["error"]["code"] == CODE

    index_run = await index_once(session, rag)
    assert (index_run.status, index_run.error) == ("failed", CODE)
