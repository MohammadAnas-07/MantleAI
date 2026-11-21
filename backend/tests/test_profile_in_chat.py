"""The project profile in real chat requests and in the context report, through the API.
Test database and FakeProvider only."""

import json
import uuid
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.modules.conversations.repository import ConversationRepository
from app.modules.llm.repository import ModelConfigRepository
from tests.api_helpers import api_client, parse_sse
from tests.query_count import count_queries
from tests.rag_helpers import RagWorld, copy_fixture, fast_settings, index_once, make_rag_world
from tests.test_rag_scanner import write

pytestmark = pytest.mark.db

FLASH, LITE = "gemini/gemini-3.8-flash", "gemini/gemini-3.5-flash-lite"


@pytest.fixture(autouse=True)
def _fast(monkeypatch: pytest.MonkeyPatch) -> None:
    fast_settings(monkeypatch)


@pytest.fixture
async def world(session: AsyncSession, tmp_path: Path) -> RagWorld:
    root = copy_fixture(tmp_path)
    write(root, "backend/pyproject.toml",
          '[project]\ndependencies = ["fastapi", "sqlalchemy"]\n')  # fmt: skip
    write(root, "web/package.json", json.dumps({"scripts": {"test": "vitest run"},
                                                "dependencies": {"react": "19"}}))  # fmt: skip
    world = await make_rag_world(session, root, name="Profiled")
    assert (await index_once(session, world)).status == "succeeded"
    return world


async def model_id(session: AsyncSession, name: str) -> uuid.UUID:
    row = await ModelConfigRepository(session).get_by_litellm_model(name)
    assert row is not None
    return row.id


async def conversation(session: AsyncSession, world: RagWorld) -> uuid.UUID:
    conv = await ConversationRepository(session, world.user_id).add(
        project_id=world.project_id, title="Chat", current_model_id=await model_id(session, FLASH)
    )
    await session.commit()
    return conv.id


def profile_block(system: str) -> str:
    start = system.index("<project_profile built=")
    return system[start : system.index("</project_profile>", start) + len("</project_profile>")]


def last_system_prompt(world: RagWorld) -> str:
    chats = [c for c in world.fake.calls if c.kind == "chat"]
    return str(chats[-1].messages[0]["content"])


async def test_a_reply_carries_the_profile(session: AsyncSession, world: RagWorld) -> None:
    conv = await conversation(session, world)
    async with api_client(session, world.gateway, world.user_id) as client:
        r = await client.post(f"/api/v1/conversations/{conv}/messages",
                              json={"content": "how do I run the tests?"})  # fmt: skip
        assert r.status_code == 200 and parse_sse(r.text)[-1][0] == "message_end"
    block = profile_block(last_system_prompt(world))
    assert "FastAPI (backend/pyproject.toml)" in block and "React (web/package.json)" in block
    assert "npm run test: vitest run (web/package.json)" in block


async def test_a_model_switch_carries_the_same_profile(
    session: AsyncSession, world: RagWorld
) -> None:
    conv = await conversation(session, world)
    async with api_client(session, world.gateway, world.user_id) as client:
        await client.post(f"/api/v1/conversations/{conv}/messages", json={"content": "hello"})
        before = profile_block(last_system_prompt(world))
        r = await client.post(f"/api/v1/conversations/{conv}/switch-model",
                              json={"model_id": str(await model_id(session, LITE)),
                                    "reason": "user_choice"})  # fmt: skip
        assert r.status_code == 200, r.text
        await client.post(f"/api/v1/conversations/{conv}/messages", json={"content": "and now?"})
    chats = [c for c in world.fake.calls if c.kind == "chat"]
    assert chats[-1].model == LITE and chats[0].model == FLASH
    assert profile_block(last_system_prompt(world)) == before


async def test_the_context_report_shows_the_profile(
    session: AsyncSession, world: RagWorld, engine: AsyncEngine
) -> None:
    conv = await conversation(session, world)
    lite = await model_id(session, LITE)
    async with api_client(session, world.gateway, world.user_id) as client:
        url = f"/api/v1/conversations/{conv}/handoff-preview"
        with count_queries(engine) as statements:
            r = await client.get(url, params={"model_id": str(lite)})
        assert r.status_code == 200, r.text
        flash = await client.get(url, params={"model_id": str(await model_id(session, FLASH))})
    report = r.json()
    section = next(s for s in report["sections"] if s["name"] == "project_profile")
    assert section["included"] and section["tokens"] > 0
    assert section["items_included"] == section["items_total"]
    other = next(s for s in flash.json()["sections"] if s["name"] == "project_profile")
    assert other["content"] == section["content"]
    assert report["profile"]["max_tokens"] == 600 and report["profile"]["dropped"] == []
    assert "languages" in report["profile"]["fields"]
    assert len([s for s in statements if "FROM project_profiles" in s]) == 1


async def test_a_tight_profile_budget_is_reported(
    session: AsyncSession, world: RagWorld, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "context_profile_max_tokens", 40)
    conv = await conversation(session, world)
    async with api_client(session, world.gateway, world.user_id) as client:
        r = await client.get(f"/api/v1/conversations/{conv}/handoff-preview",
                             params={"model_id": str(await model_id(session, FLASH))})  # fmt: skip
    report = r.json()
    dropped = report["profile"]["dropped"]
    assert dropped and dropped[0] == {"field": "layout", "reason": "profile_budget"}
    assert "profile layout" in report["dropped"]


async def test_a_project_without_a_profile_has_no_section(
    session: AsyncSession, tmp_path: Path
) -> None:
    world = await make_rag_world(session, tmp_path, name="Bare")
    conv = await conversation(session, world)
    async with api_client(session, world.gateway, world.user_id) as client:
        r = await client.get(f"/api/v1/conversations/{conv}/handoff-preview",
                             params={"model_id": str(await model_id(session, FLASH))})  # fmt: skip
    section = next(s for s in r.json()["sections"] if s["name"] == "project_profile")
    assert section["included"] is False and r.json()["profile"]["fields"] == []
