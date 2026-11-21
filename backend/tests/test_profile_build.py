"""The profile is rebuilt at the end of every successful index run (test database, fake
embeddings). A failed or cancelled run leaves the last profile as it was."""

import json
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.modules.rag import indexer
from app.modules.rag.repository import ProjectProfileRepository
from tests.rag_helpers import fast_settings, index_once, make_rag_world
from tests.test_rag_scanner import write

pytestmark = pytest.mark.db


@pytest.fixture(autouse=True)
def _fast(monkeypatch: pytest.MonkeyPatch) -> None:
    fast_settings(monkeypatch)


def node_project(root: Path) -> None:
    write(root, "package.json", json.dumps({"scripts": {"test": "vitest run"},
                                            "dependencies": {"react": "19"}}))  # fmt: skip
    write(root, "src/main.tsx", "export const App = 1;\n")


async def test_a_successful_run_builds_the_profile(session: AsyncSession, tmp_path: Path) -> None:
    node_project(tmp_path)
    world = await make_rag_world(session, tmp_path, name="Built")
    run = await index_once(session, world)
    assert run.status == "succeeded"
    profile = await ProjectProfileRepository(session, world.user_id).get_for_project(
        world.project_id)  # fmt: skip
    assert profile is not None and profile.index_run_id == run.id and profile.built_at
    assert [f["name"] for f in profile.frameworks] == ["React"]
    assert profile.languages == {"json": 1, "tsx": 1}

    write(tmp_path, "pyproject.toml", '[project]\ndependencies = ["fastapi"]\n')
    again = await index_once(session, world)
    profile = await ProjectProfileRepository(session, world.user_id).get_for_project(
        world.project_id)  # fmt: skip
    assert profile is not None and profile.index_run_id == again.id
    assert [f["name"] for f in profile.frameworks] == ["FastAPI", "React"]


async def test_a_failed_run_keeps_the_last_profile(
    session: AsyncSession, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    node_project(tmp_path)
    world = await make_rag_world(session, tmp_path, name="Kept")
    first = await index_once(session, world)
    for i in range(30):
        write(tmp_path, f"img/{i}.png", b"\x89PNG")
    monkeypatch.setattr(settings, "index_max_entries", 10)
    failed = await index_once(session, world)
    assert failed.status == "failed"
    profile = await ProjectProfileRepository(session, world.user_id).get_for_project(
        world.project_id)  # fmt: skip
    assert profile is not None and profile.index_run_id == first.id


async def test_a_profile_error_does_not_fail_the_run(
    session: AsyncSession, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:  # fmt: skip
    node_project(tmp_path)

    def broken(*args: object, **kwargs: object) -> dict[str, object]:
        raise ValueError("vitest run from package.json")  # text that must not reach the log

    monkeypatch.setattr(indexer, "collect_facts", broken)
    world = await make_rag_world(session, tmp_path, name="Broken")
    run = await index_once(session, world)
    assert run.status == "succeeded" and run.files_indexed == 2
    assert await ProjectProfileRepository(session, world.user_id).get_for_project(
        world.project_id) is None  # fmt: skip
    assert "profile build failed" in caplog.text and "ValueError" in caplog.text
    assert "vitest" not in caplog.text and "package.json" not in caplog.text
