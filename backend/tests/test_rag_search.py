"""Hybrid search and the rag endpoints, on the test database with FakeProvider embeddings.

FakeProvider embeds texts as bag-of-words vectors, so texts that share words are close. That
is enough to check ranking logic, filters, fusion and isolation; it says nothing about how
well a real embedding model understands code (scripts/eval_retrieval.py measures that).
"""

import uuid
from pathlib import Path

import pytest
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.modules.llm.repository import UsageRecordRepository
from app.modules.rag.search import Hit, merge_adjacent, query_terms
from app.modules.rag.service import NotIndexed, search
from tests.api_helpers import api_client
from tests.rag_helpers import RagWorld, copy_fixture, fast_settings, index_once, make_rag_world

pytestmark = pytest.mark.db


@pytest.fixture(autouse=True)
def _fast(monkeypatch: pytest.MonkeyPatch) -> None:
    fast_settings(monkeypatch)


@pytest.fixture
async def world(session: AsyncSession, tmp_path: Path) -> RagWorld:
    world = await make_rag_world(session, copy_fixture(tmp_path))
    run = await index_once(session, world)
    assert run.status == "succeeded"
    return world


async def find(session: AsyncSession, world: RagWorld, query: str, **kwargs: object) -> list[str]:
    result = await search(session, world.gateway, world.user_id, world.project_id, query, **kwargs)
    return [b.path for b in result.blocks]


# ---- ranking -------------------------------------------------------------------------------


async def test_vector_ranking_on_fake_embeddings(session: AsyncSession, world: RagWorld) -> None:
    paths = await find(session, world, "health check timeout seconds", mode="vector")
    assert paths[0] == "backend/app/main.py"
    paths = await find(session, world, "token bucket refill rate capacity", mode="vector")
    assert paths[0] == "backend/app/rate_limit.py"


async def test_text_ranking_splits_identifiers(session: AsyncSession, world: RagWorld) -> None:
    # "debounced" never appears as written; useDebounce is split into "use debounce".
    paths = await find(session, world, "useDebounce delay", mode="text")
    assert paths[0] == "web/src/hooks/useDebounce.ts"


async def test_query_embedding_is_logged_as_embedding(
    session: AsyncSession, world: RagWorld
) -> None:
    world.fake.calls.clear()
    await find(session, world, "session token lifetime")
    [call] = world.fake.calls
    assert call.input_type == "query"
    usage = await UsageRecordRepository(session, world.user_id).list(limit=1000)
    assert {u.purpose for u in usage} == {"embedding"}


async def test_hybrid_beats_either_arm_alone(session: AsyncSession, tmp_path: Path) -> None:
    """The target is second in both arms; each decoy is first in one arm only."""
    root = tmp_path / "crafted"
    root.mkdir()
    # Close by vector (shares the query's common words), no full-text match at all.
    (root / "vector_decoy.md").write_text("how is the " * 5 + "\n")
    # Strong full-text match through split identifiers, but no shared word for the vector.
    (root / "text_decoy.md").write_text("signingKeyRotated signingKeyRotated rotatedSigningKey\n")
    # Shares some words with both.
    (root / "target.md").write_text("the signing key is rotated every week by a cron job\n")
    # Fillers that share a little with the query, so the text decoy ranks low by vector.
    (root / "filler_one.md").write_text("the build is fast\n")
    (root / "filler_two.md").write_text("how the cache is warmed\n")
    world = await make_rag_world(session, root, name="Crafted")
    await index_once(session, world)
    query = "how is the signing key rotated"

    vector = await find(session, world, query, mode="vector")
    text = await find(session, world, query, mode="text")
    hybrid = await find(session, world, query, mode="hybrid")
    assert vector[:2] == ["vector_decoy.md", "target.md"]
    assert text[:2] == ["text_decoy.md", "target.md"]
    assert hybrid[0] == "target.md"


async def test_filters_by_path_prefix_and_language(session: AsyncSession, world: RagWorld) -> None:
    web = await find(session, world, "task due date overdue", path_prefix="web/")
    assert web and all(p.startswith("web/") for p in web)
    python = await find(session, world, "task due date overdue", language="python")
    assert python and all(p.endswith(".py") for p in python)
    # A prefix with LIKE wildcards matches literally.
    assert await find(session, world, "task", path_prefix="w%") == []


async def test_top_k_and_no_matches(session: AsyncSession, world: RagWorld) -> None:
    result = await search(session, world.gateway, world.user_id, world.project_id,
                          "task", top_k=2)  # fmt: skip
    assert len(result.blocks) <= 2
    assert await find(session, world, "zzqx", mode="text") == []


def test_merge_adjacent_and_overlapping_hits() -> None:
    doc = uuid.uuid4()

    def hit(start: int, end: int, score: float, path: str = "a.py") -> Hit:
        text = "\n".join(f"line {n}" for n in range(start, end + 1))
        return Hit(uuid.uuid4(), doc, path, start, end, "python", None, text, score, 1, None)

    blocks = merge_adjacent(
        [
            hit(1, 10, 0.02),
            hit(8, 15, 0.03),
            hit(18, 20, 0.01),
            hit(40, 45, 0.05),
            hit(1, 3, 0.04, "b.py"),
        ]  # fmt: skip
    )
    spans = [(b.path, b.start_line, b.end_line, len(b.chunk_ids)) for b in blocks]
    assert spans == [("a.py", 40, 45, 1), ("b.py", 1, 3, 1), ("a.py", 1, 20, 3)]
    merged = blocks[2]
    assert merged.score == 0.03
    lines = merged.text.split("\n")
    assert lines[0] == "line 1" and lines[14] == "line 15" and lines[15:17] == ["", ""]
    assert lines[-1] == "line 20"


async def test_merge_in_a_real_search(session: AsyncSession, world: RagWorld) -> None:
    result = await search(session, world.gateway, world.user_id, world.project_id,
                          "verify password session token hmac", top_k=10)  # fmt: skip
    auth = [b for b in result.blocks if b.path == "backend/app/auth.py"]
    assert len(auth) == 1 and len(auth[0].chunk_ids) >= 2


def test_query_terms_drop_stop_words() -> None:
    assert query_terms("Where is the healthCheck timeout set?") == [
        "healthcheck", "health", "check", "timeout",
    ]  # fmt: skip


# ---- errors and isolation ------------------------------------------------------------------


async def test_unindexed_project(session: AsyncSession, tmp_path: Path) -> None:
    world = await make_rag_world(session, copy_fixture(tmp_path), name="Fresh")
    with pytest.raises(NotIndexed):
        await search(session, world.gateway, world.user_id, world.project_id, "health")


async def test_isolation_between_users_and_projects(
    session: AsyncSession, world: RagWorld, tmp_path: Path
) -> None:
    other_root = tmp_path / "other"
    other_root.mkdir()
    (other_root / "notes.md").write_text("# Notes\n\nThe health of the garden plants.\n")
    other = await make_rag_world(session, other_root, name="Other user")
    await index_once(session, other)
    paths = await find(session, other, "health check timeout")
    assert paths == ["notes.md"]
    # The same user's second project sees only its own files.
    from app.modules.projects.repository import ProjectRepository

    second = await ProjectRepository(session, world.user_id).add(
        name="Second", root_path=str(other_root.resolve())
    )
    second_world = RagWorld(world.user_id, second.id, other_root, world.fake, world.gateway)
    await index_once(session, second_world)
    assert await find(session, second_world, "health check timeout") == ["notes.md"]
    assert "notes.md" not in await find(session, world, "garden plants health")


# ---- endpoints -----------------------------------------------------------------------------


async def test_index_flow_through_the_api(session: AsyncSession, tmp_path: Path) -> None:
    root = copy_fixture(tmp_path)
    world = await make_rag_world(session, root, name="Api")
    async with api_client(session, world.gateway, world.user_id) as client:
        pid = world.project_id
        raw = str(root).replace("/", "\\")
        r = await client.put(f"/api/v1/projects/{pid}/source", json={"root_path": raw})
        assert r.status_code == 200, r.text
        assert r.json()["indexed"] is False

        r = await client.post(f"/api/v1/projects/{pid}/index/estimate", json={})
        assert r.status_code == 200 and r.json()["provider"] == "google"

        r = await client.post(f"/api/v1/projects/{pid}/index", json={})
        assert r.status_code == 202, r.text
        run_id = r.json()["run_id"]
        r = await client.get(f"/api/v1/index-runs/{run_id}")
        assert r.json()["status"] == "succeeded"
        assert (await client.get(f"/api/v1/projects/{pid}/index-runs")).json()[0]["id"] == run_id

        r = await client.get(f"/api/v1/projects/{pid}")
        body = r.json()
        assert body["indexed"] and body["last_indexed_at"] and not body["needs_reindex"]

        r = await client.get(f"/api/v1/projects/{pid}/documents", params={"status": "indexed"})
        assert r.json()["total"] >= 15

        r = await client.post(f"/api/v1/projects/{pid}/search", json={"query": "health timeout"})
        assert r.status_code == 200
        first = r.json()["results"][0]
        assert {"path", "start_line", "end_line", "vector_rank", "text_rank", "score"} <= set(first)

        r = await client.post(f"/api/v1/projects/{pid}/search", json={"query": "   "})
        assert (r.status_code, r.json()["error"]["code"]) == (422, "invalid_query")
        long = "x" * (settings.retrieval_query_max_chars + 1)
        r = await client.post(f"/api/v1/projects/{pid}/search", json={"query": long})
        assert (r.status_code, r.json()["error"]["code"]) == (422, "invalid_query")
        r = await client.post(f"/api/v1/projects/{pid}/search", json={"query": "x", "top_k": 999})
        assert r.status_code == 422

        r = await client.delete(f"/api/v1/projects/{pid}/index")
        assert r.status_code == 204
        assert (await client.get(f"/api/v1/projects/{pid}/documents")).json()["total"] == 0
        r = await client.post(f"/api/v1/projects/{pid}/search", json={"query": "health"})
        assert (r.status_code, r.json()["error"]["code"]) == (409, "not_indexed")


async def test_source_path_errors_through_the_api(session: AsyncSession, tmp_path: Path) -> None:
    world = await make_rag_world(session, tmp_path, name="Paths")
    async with api_client(session, world.gateway, world.user_id) as client:
        url = f"/api/v1/projects/{world.project_id}/source"
        r = await client.put(url, json={"root_path": str(tmp_path / "missing")})
        assert r.status_code == 422
        assert r.json()["error"]["details"]["reason"] == "missing"
        r = await client.post(
            "/api/v1/projects", json={"name": "P", "root_path": str(Path.cwd().anchor)}
        )
        assert r.json()["error"]["details"]["reason"] == "filesystem_root"


async def test_other_users_project_is_404(session: AsyncSession, world: RagWorld) -> None:
    other = await make_rag_world(session, world.root, name="Intruder")
    async with api_client(session, other.gateway, other.user_id) as client:
        pid = world.project_id
        for method, url, body in (
            ("get", f"/api/v1/projects/{pid}", None),
            ("get", f"/api/v1/projects/{pid}/index", None),
            ("get", f"/api/v1/projects/{pid}/documents", None),
            ("post", f"/api/v1/projects/{pid}/search", {"query": "health"}),
            ("post", f"/api/v1/projects/{pid}/index", {}),
            ("delete", f"/api/v1/projects/{pid}/index", None),
        ):
            r = await client.request(method, url, json=body)
            assert r.status_code == 404, (method, url, r.text)


async def test_search_endpoint_is_dev_only(
    session: AsyncSession, world: RagWorld, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "app_env", "production")
    async with api_client(session, world.gateway, world.user_id) as client:
        r = await client.post(
            f"/api/v1/projects/{world.project_id}/search", json={"query": "health"}
        )
        assert r.status_code == 404


async def test_second_index_request_is_409(session: AsyncSession, world: RagWorld) -> None:
    from app.modules.rag.service import start_index

    await start_index(session, world.user_id, world.project_id)
    async with api_client(session, world.gateway, world.user_id) as client:
        r = await client.post(f"/api/v1/projects/{world.project_id}/index", json={})
        assert (r.status_code, r.json()["error"]["code"]) == (409, "index_in_progress")


async def test_project_list_runs_a_fixed_number_of_queries(
    session: AsyncSession, world: RagWorld
) -> None:
    from app.modules.projects.repository import ProjectRepository

    statements: list[str] = []

    def count(*args: object) -> None:
        statements.append(str(args[2]))

    engine = session.bind.engine.sync_engine  # type: ignore[union-attr]
    async with api_client(session, world.gateway, world.user_id) as client:
        event.listen(engine, "before_cursor_execute", count)
        try:
            await client.get("/api/v1/projects")
            one = len(statements)
            for i in range(4):
                await ProjectRepository(session, world.user_id).add(name=f"P{i}")
            statements.clear()
            r = await client.get("/api/v1/projects")
            five = len(statements)
        finally:
            event.remove(engine, "before_cursor_execute", count)
    assert len(r.json()) == 5
    assert five == one
