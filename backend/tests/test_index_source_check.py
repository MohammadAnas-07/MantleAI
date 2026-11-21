"""The source folder is checked again when indexing starts (audit A-010): a folder saved before
the rules, or a link changed since, can't be indexed. Test database, FakeProvider."""

from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from tests.api_helpers import api_client
from tests.rag_helpers import make_rag_world

pytestmark = pytest.mark.db


async def test_a_saved_sensitive_folder_is_refused_at_start(
    session: AsyncSession, fake_home: Path
) -> None:
    folder = fake_home / ".aws" / "notes"
    folder.mkdir(parents=True)
    (folder / "readme.md").write_text("# notes\n")
    world = await make_rag_world(session, folder, name="Saved")  # stored without the check
    async with api_client(session, world.gateway, world.user_id) as client:
        pid = world.project_id
        for url in (f"/api/v1/projects/{pid}/index", f"/api/v1/projects/{pid}/index/estimate"):
            r = await client.post(url, json={})
            assert r.status_code == 422, r.text
            error = r.json()["error"]
            assert (error["code"], error["details"]["reason"]) == (
                "invalid_source_path", "sensitive_folder")  # fmt: skip
            assert "Traceback" not in r.text and str(folder) not in r.text
        runs = (await client.get(f"/api/v1/projects/{pid}/index-runs")).json()
        assert runs == []
    assert world.fake.calls == []


async def test_saving_a_sensitive_folder_is_refused(
    session: AsyncSession, fake_home: Path, tmp_path: Path
) -> None:
    (fake_home / "AppData" / "Roaming").mkdir(parents=True)
    world = await make_rag_world(session, tmp_path, name="Put")
    async with api_client(session, world.gateway, world.user_id) as client:
        roaming = str(fake_home / "AppData" / "Roaming")
        r = await client.put(f"/api/v1/projects/{world.project_id}/source",
                             json={"root_path": roaming})  # fmt: skip
        assert r.status_code == 422
        assert r.json()["error"]["details"]["reason"] == "sensitive_folder"
        r = await client.post("/api/v1/projects",
                              json={"name": "Home", "root_path": str(fake_home)})  # fmt: skip
        assert r.json()["error"]["details"]["reason"] == "home"
