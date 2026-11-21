"""Folder scan limits (audit A-021): a depth cap, link loops, and a cap on the entries one run
looks at. Generated folders in tmp_path; the run tests use the test database."""

from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.modules.rag.models import Document
from app.modules.rag.scanner import SkipReason, WalkLimits, walk
from tests.rag_helpers import fast_settings, index_once, make_rag_world
from tests.test_rag_scanner import link_dir, write


def deep_tree(root: Path, levels: int) -> Path:
    folder = root
    for i in range(levels):
        folder = folder / f"d{i}"
    write(folder, "leaf.py")
    write(root, "top.py")
    return folder


def test_a_tree_deeper_than_the_limit_is_cut_with_a_reason(tmp_path: Path) -> None:
    deep_tree(tmp_path, 12)
    result = walk(tmp_path, WalkLimits(10**6, 1000, max_depth=5))
    assert [f.path for f in result.files] == ["top.py"]
    assert result.report.counts[SkipReason.TOO_DEEP] == 1
    assert result.stopped is None
    assert not any(s.reason == SkipReason.TOO_DEEP for s in result.skipped if s.path == "top.py")


def test_files_at_the_depth_limit_are_still_indexed(tmp_path: Path) -> None:
    deep_tree(tmp_path, 5)
    paths = [f.path for f in walk(tmp_path, WalkLimits(10**6, 1000, max_depth=5)).files]
    assert "d0/d1/d2/d3/d4/leaf.py" in paths


def test_the_default_depth_walks_a_deep_tree_without_a_crash(tmp_path: Path) -> None:
    # Windows paths stay short enough with one-letter folders.
    folder = tmp_path
    for _ in range(settings.index_max_depth + 20):
        folder = folder / "a"
    try:
        folder.mkdir(parents=True)
    except OSError:
        pytest.skip("this system can't make a path that long")
    write(folder, "leaf.py")
    result = walk(tmp_path, WalkLimits(10**6, 1000, max_depth=settings.index_max_depth))
    assert result.files == [] and result.report.counts[SkipReason.TOO_DEEP] == 1


def test_a_link_loop_ends(tmp_path: Path) -> None:
    write(tmp_path, "pkg/main.py")
    link_dir(tmp_path / "pkg" / "loop", tmp_path)  # pkg/loop -> the root
    result = walk(tmp_path, WalkLimits(10**6, 1000))
    assert [f.path for f in result.files] == ["pkg/main.py"]
    assert {s.path: s.reason for s in result.skipped}["pkg/loop"] == SkipReason.SYMLINK


def test_too_many_entries_stops_the_walk_with_counts(tmp_path: Path) -> None:
    for i in range(300):
        write(tmp_path, f"img/{i:04}.png", b"\x89PNG")
    write(tmp_path, "zz/main.py")
    result = walk(tmp_path, WalkLimits(10**6, 1000, max_entries=100))
    assert result.stopped == SkipReason.TOO_MANY_ENTRIES
    assert result.entries_seen == 100
    assert len(result.skipped) <= 100  # not one row per file of the whole tree
    assert result.report.as_dict()[SkipReason.TOO_MANY_ENTRIES] == {"count": 100, "examples": []}


# ---- through a run -------------------------------------------------------------------------


@pytest.mark.db
async def test_a_run_over_the_entry_cap_fails_with_a_reason_and_keeps_the_index(
    session: AsyncSession, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:  # fmt: skip
    fast_settings(monkeypatch)
    write(tmp_path, "app/main.py", "def main():\n    return 1\n")
    world = await make_rag_world(session, tmp_path, name="Huge")
    first = await index_once(session, world)
    assert first.status == "succeeded"

    for i in range(150):
        write(tmp_path, f"assets/secret-name-{i:04}.png", b"\x89PNG")
    monkeypatch.setattr(settings, "index_max_entries", 50)
    run = await index_once(session, world)
    assert (run.status, run.error) == ("failed", "too_many_entries")
    assert run.skip_report[SkipReason.TOO_MANY_ENTRIES]["count"] == 50
    mine = (Document.user_id == world.user_id, Document.project_id == world.project_id)
    docs = (await session.scalars(select(Document.path).where(*mine))).all()
    assert list(docs) == ["app/main.py"]  # nothing added, nothing deleted
    assert "secret-name" not in caplog.text


@pytest.mark.db
async def test_a_too_deep_folder_is_reported_on_a_good_run(
    session: AsyncSession, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fast_settings(monkeypatch)
    monkeypatch.setattr(settings, "index_max_depth", 3)
    deep_tree(tmp_path, 6)
    world = await make_rag_world(session, tmp_path, name="Deep")
    run = await index_once(session, world)
    assert run.status == "succeeded" and run.files_indexed == 1
    assert run.skip_report[SkipReason.TOO_DEEP]["count"] == 1
    total = await session.scalar(select(func.count()).select_from(Document).where(
        Document.user_id == world.user_id))  # fmt: skip
    assert total == 1  # a cut folder is in the report, not one row per file
