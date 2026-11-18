"""PATCH and DELETE /projects/{id}. FakeProvider only."""

import uuid
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.conversations.repository import ConversationRepository
from app.modules.llm.repository import ModelConfigRepository
from app.modules.rag.models import Document
from app.modules.rag.service import start_index
from tests.api_helpers import api_client
from tests.rag_helpers import copy_fixture, fast_settings, index_once, make_rag_world

pytestmark = pytest.mark.db


@pytest.fixture(autouse=True)
def _fast(monkeypatch: pytest.MonkeyPatch) -> None:
    fast_settings(monkeypatch)


async def test_rename_and_set_default_model(session: AsyncSession, tmp_path: Path) -> None:
    world = await make_rag_world(session, tmp_path)
    chat = await ModelConfigRepository(session).get_by_litellm_model("openai/gpt-5.6")
    assert chat is not None  # no OpenAI key in this world: allowed, the UI warns
    async with api_client(session, world.gateway, world.user_id) as client:
        url = f"/api/v1/projects/{world.project_id}"
        r = await client.patch(url, json={"name": "Renamed", "default_model_id": str(chat.id)})
        assert r.status_code == 200, r.text
        assert (r.json()["name"], r.json()["default_model_id"]) == ("Renamed", str(chat.id))
        r = await client.patch(url, json={"default_model_id": None})
        assert r.json()["default_model_id"] is None and r.json()["name"] == "Renamed"


async def test_patch_errors(session: AsyncSession, tmp_path: Path) -> None:
    world = await make_rag_world(session, tmp_path)
    embed = await ModelConfigRepository(session).get_by_litellm_model("gemini/gemini-embedding-001")
    assert embed is not None
    async with api_client(session, world.gateway, world.user_id) as client:
        url = f"/api/v1/projects/{world.project_id}"
        r = await client.patch(url, json={"default_model_id": str(uuid.uuid4())})
        assert (r.status_code, r.json()["error"]["code"]) == (422, "model_unavailable")
        r = await client.patch(url, json={"default_model_id": str(embed.id)})  # not a chat model
        assert r.status_code == 422
        assert (await client.patch(url, json={})).status_code == 422
        assert (await client.patch(url, json={"name": ""})).status_code == 422
        assert (await client.patch(url, json={"name": None})).status_code == 422
        assert (await client.patch(url, json={"root_path": "/x"})).status_code == 422
        r = await client.patch(f"/api/v1/projects/{uuid.uuid4()}", json={"name": "x"})
        assert r.status_code == 404


async def test_delete_cascades(session: AsyncSession, tmp_path: Path) -> None:
    world = await make_rag_world(session, copy_fixture(tmp_path))
    await index_once(session, world)
    chat = await ModelConfigRepository(session).get_by_litellm_model("gemini/gemini-3.8-flash")
    assert chat is not None
    await ConversationRepository(session, world.user_id).add(
        project_id=world.project_id, current_model_id=chat.id
    )
    async with api_client(session, world.gateway, world.user_id) as client:
        r = await client.delete(f"/api/v1/projects/{world.project_id}")
        assert r.status_code == 204
        assert (await client.get(f"/api/v1/projects/{world.project_id}")).status_code == 404
    docs = await session.scalar(
        select(func.count()).select_from(Document).where(Document.project_id == world.project_id)
    )
    assert docs == 0


async def test_delete_while_indexing_is_409(session: AsyncSession, tmp_path: Path) -> None:
    world = await make_rag_world(session, copy_fixture(tmp_path))
    await start_index(session, world.user_id, world.project_id)
    async with api_client(session, world.gateway, world.user_id) as client:
        r = await client.delete(f"/api/v1/projects/{world.project_id}")
        assert (r.status_code, r.json()["error"]["code"]) == (409, "index_in_progress")


async def test_other_users_project(session: AsyncSession, tmp_path: Path) -> None:
    world = await make_rag_world(session, tmp_path)
    other = await make_rag_world(session, tmp_path, name="Other")
    async with api_client(session, other.gateway, other.user_id) as client:
        url = f"/api/v1/projects/{world.project_id}"
        assert (await client.patch(url, json={"name": "x"})).status_code == 404
        assert (await client.delete(url)).status_code == 404
