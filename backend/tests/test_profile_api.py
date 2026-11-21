"""GET /api/v1/projects/{id}/profile (test database, FakeProvider embeddings)."""

import json
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.config import settings
from tests.api_helpers import api_client
from tests.query_count import count_queries
from tests.rag_helpers import RagWorld, fast_settings, index_once, make_rag_world
from tests.test_rag_scanner import write

pytestmark = pytest.mark.db


@pytest.fixture(autouse=True)
def _fast(monkeypatch: pytest.MonkeyPatch) -> None:
    fast_settings(monkeypatch)


def project(root: Path) -> None:
    write(root, "pyproject.toml", '[project]\ndependencies = ["fastapi"]\n')
    write(root, "app/main.py", "app = 1\n")
    write(root, "app/models.py", "x = 1\n")
    write(root, "web/package.json", json.dumps({"scripts": {"dev": "vite"}}))


def url(world: RagWorld) -> str:
    return f"/api/v1/projects/{world.project_id}/profile"


async def test_before_the_first_index_run_there_is_no_profile(
    session: AsyncSession, tmp_path: Path
) -> None:
    world = await make_rag_world(session, tmp_path, name="New")
    async with api_client(session, world.gateway, world.user_id) as client:
        body = (await client.get(url(world))).json()
    assert body["built"] is False and body["built_at"] is None and body["index_run_id"] is None
    assert body["languages"] == [] and body["commands"] == []
    assert body["out_of_date"] is False


async def test_the_profile_after_an_index_run(
    session: AsyncSession, tmp_path: Path, engine: AsyncEngine
) -> None:
    project(tmp_path)
    world = await make_rag_world(session, tmp_path, name="Api")
    run = await index_once(session, world)
    async with api_client(session, world.gateway, world.user_id) as client:
        with count_queries(engine) as statements:
            r = await client.get(url(world))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["built"] and body["index_run_id"] == str(run.id) and not body["out_of_date"]
    languages = {x["name"]: x for x in body["languages"]}
    assert languages["python"]["files"] == 2
    assert abs(sum(x["share"] for x in body["languages"]) - 1) < 0.01
    assert body["frameworks"] == [{"name": "FastAPI", "source": "pyproject.toml"}]
    assert body["commands"] == [{"name": "npm run dev", "command": "vite",
                                 "source": "web/package.json", "kind": "script"}]  # fmt: skip
    assert {"source": "app/main.py", "kind": "python"} in body["entry_points"]
    assert len(statements) <= 4, statements


async def test_a_new_folder_makes_the_profile_out_of_date(
    session: AsyncSession, tmp_path: Path
) -> None:
    project(tmp_path / "one")
    write(tmp_path / "two", "main.py")
    world = await make_rag_world(session, tmp_path / "one", name="Moved")
    await index_once(session, world)
    async with api_client(session, world.gateway, world.user_id) as client:
        r = await client.put(f"/api/v1/projects/{world.project_id}/source",
                             json={"root_path": str(tmp_path / "two")})  # fmt: skip
        assert r.status_code == 200
        body = (await client.get(url(world))).json()
    assert body["built"] and body["out_of_date"]
    assert body["out_of_date_reasons"] == ["source_changed"]


async def test_a_later_failed_run_makes_the_profile_out_of_date(
    session: AsyncSession, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project(tmp_path)
    world = await make_rag_world(session, tmp_path, name="Failed")
    first = await index_once(session, world)
    for i in range(30):
        write(tmp_path, f"img/{i}.png", b"\x89PNG")
    monkeypatch.setattr(settings, "index_max_entries", 10)
    assert (await index_once(session, world)).status == "failed"
    async with api_client(session, world.gateway, world.user_id) as client:
        body = (await client.get(url(world))).json()
    assert body["index_run_id"] == str(first.id)
    assert body["out_of_date_reasons"] == ["index_changed"]


async def test_another_users_project_is_404(session: AsyncSession, tmp_path: Path) -> None:
    project(tmp_path)
    mine = await make_rag_world(session, tmp_path, name="Mine")
    other = await make_rag_world(session, tmp_path, name="Other")
    await index_once(session, mine)
    async with api_client(session, other.gateway, other.user_id) as client:
        r = await client.get(url(mine))
    assert r.status_code == 404
