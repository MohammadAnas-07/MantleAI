"""The incremental indexing job, end to end on the test database. FakeProvider only."""

import logging
import uuid
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.modules.llm.backend import EmbedResult
from app.modules.llm.fake import FakeProvider
from app.modules.llm.repository import (
    ModelConfigRepository,
    ProviderCredentialRepository,
    UsageRecordRepository,
    UserModelSettingsRepository,
)
from app.modules.llm.service import AuthFailed, RateLimited
from app.modules.rag.models import Chunk, IndexRun
from app.modules.rag.service import (
    CostLimitExceeded,
    IndexInProgress,
    NoSourcePath,
    cancel_run,
    estimate_index,
    index_status,
    recover_interrupted_runs,
    search,
    start_index,
)
from tests.rag_helpers import (
    GEMINI,
    RagWorld,
    copy_fixture,
    count_chunks,
    documents,
    embedded_texts,
    fast_settings,
    index_once,
    make_rag_world,
)

pytestmark = pytest.mark.db


@pytest.fixture(autouse=True)
def _fast(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    return fast_settings(monkeypatch)


@pytest.fixture
def root(tmp_path: Path) -> Path:
    return copy_fixture(tmp_path)


@pytest.fixture
async def world(session: AsyncSession, root: Path) -> RagWorld:
    return await make_rag_world(session, root)


class FlakyProvider(FakeProvider):
    """Raises `error` on embed calls number `fail_on` (1-based), and works otherwise."""

    def __init__(self, error: Exception, fail_on: set[int]) -> None:
        super().__init__()
        self.error = error
        self.fail_on = fail_on
        self.embed_calls = 0

    async def embed(self, model: str, texts: list[str], **kwargs: object) -> EmbedResult:
        self.embed_calls += 1
        if self.embed_calls in self.fail_on:
            raise self.error
        return await super().embed(model, texts, **kwargs)  # type: ignore[arg-type]


async def test_first_run_indexes_the_sample_project(session: AsyncSession, world: RagWorld) -> None:
    run = await index_once(session, world)
    assert run.status == "succeeded", run.error
    docs = await documents(session, world)
    indexed = {p for p, d in docs.items() if d.status == "indexed"}
    assert "backend/app/main.py" in indexed and "web/src/api/client.ts" in indexed
    assert "docs/deployment.md" in indexed
    assert run.files_indexed == len(indexed) >= 15
    assert run.chunks_created == await count_chunks(session, world) > 0
    assert run.tokens > 0 and run.cost_estimate_usd is not None
    # Every chunk is stored with the model name and dimension.
    chunks = await session.scalars(select(Chunk).where(Chunk.project_id == world.project_id))
    for chunk in chunks:
        assert (chunk.embedding_model, chunk.embedding_dimensions) == (GEMINI, 1536)
        assert chunk.content_hash and chunk.search_text
    # One usage row per batch, all "embedding", sent as documents.
    usage = await UsageRecordRepository(session, world.user_id).list(limit=1000)
    assert usage and {(u.purpose, u.trigger, u.status) for u in usage} == {
        ("embedding", "user", "success")
    }
    assert {c.input_type for c in world.fake.calls} == {"document"}
    status = await index_status(session, world.user_id, world.project_id)
    assert status.indexed and not status.needs_reindex and status.last_indexed_at


async def test_rerun_embeds_nothing(session: AsyncSession, world: RagWorld) -> None:
    await index_once(session, world)
    world.fake.calls.clear()
    run = await index_once(session, world)
    assert run.status == "succeeded"
    assert embedded_texts(world.fake) == []
    assert run.files_indexed == 0 and run.files_unchanged >= 15


async def test_changed_file_re_embeds_only_changed_segments(
    session: AsyncSession, world: RagWorld, root: Path
) -> None:
    await index_once(session, world)
    before = await count_chunks(session, world)
    world.fake.calls.clear()
    path = root / "backend" / "app" / "rate_limit.py"
    text = path.read_text().replace("missing / bucket.rate", "missing / max(bucket.rate, 0.1)")
    path.write_text(text)
    run = await index_once(session, world)
    assert run.files_indexed == 1
    sent = embedded_texts(world.fake)
    assert len(sent) == 1 and "retry_after_seconds" in sent[0]
    assert await count_chunks(session, world) == before
    hits = await search(session, world.gateway, world.user_id, world.project_id,
                        "retry_after_seconds", mode="text")  # fmt: skip
    assert hits.blocks[0].path == "backend/app/rate_limit.py"
    assert "max(bucket.rate, 0.1)" in hits.blocks[0].text


async def test_touched_but_identical_file_is_not_re_embedded(
    session: AsyncSession, world: RagWorld, root: Path
) -> None:
    await index_once(session, world)
    world.fake.calls.clear()
    path = root / "README.md"
    path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))  # CRLF: same normalized text
    run = await index_once(session, world)
    assert embedded_texts(world.fake) == [] and run.files_unchanged >= 15


async def test_deleted_and_renamed_files(
    session: AsyncSession, world: RagWorld, root: Path
) -> None:
    await index_once(session, world)
    (root / "docs" / "architecture.md").unlink()
    (root / "backend" / "app" / "email.py").rename(root / "backend" / "app" / "mailer.py")
    await index_once(session, world)
    docs = await documents(session, world)
    assert "docs/architecture.md" not in docs
    assert "backend/app/email.py" not in docs
    assert docs["backend/app/mailer.py"].status == "indexed"
    orphans = await session.scalar(
        select(Chunk.id).where(
            Chunk.project_id == world.project_id,
            Chunk.document_id.not_in([d.id for d in docs.values()]),
        )
    )
    assert orphans is None


async def test_failure_midway_then_resume(
    session: AsyncSession, root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "embed_batch_max_items", 4)
    flaky = FlakyProvider(AuthFailed("bad key"), fail_on={3})
    world = await make_rag_world(session, root, flaky)
    run = await index_once(session, world)
    assert (run.status, run.error) == ("failed", "auth_failed")
    stored = await count_chunks(session, world)
    assert stored == 8  # the two finished batches stay
    first_total = run.estimate["segments_to_embed"]

    flaky.fail_on = set()
    flaky.calls.clear()
    run = await index_once(session, world)
    assert run.status == "succeeded"
    assert len(embedded_texts(flaky)) == first_total - stored  # only what was missing
    status = await index_status(session, world.user_id, world.project_id)
    assert status.indexed


async def test_rate_limit_backs_off_and_succeeds(
    session: AsyncSession, root: Path, monkeypatch: pytest.MonkeyPatch, _fast: list[float]
) -> None:
    monkeypatch.setattr(settings, "embed_rate_limit_backoff_seconds", 5.0)
    monkeypatch.setattr(settings, "embed_rate_limit_backoff_max_seconds", 8.0)
    flaky = FlakyProvider(RateLimited("slow down"), fail_on={1, 2, 3})
    world = await make_rag_world(session, root, flaky)
    run = await index_once(session, world)
    assert run.status == "succeeded"
    assert _fast == [5.0, 8.0, 8.0]  # doubling, capped
    usage = await UsageRecordRepository(session, world.user_id).list(limit=1000)
    assert [u.error_code for u in usage if u.status == "error"] == ["rate_limited"] * 3


async def test_rate_limit_fails_after_retry_cap_and_rerun_resumes(
    session: AsyncSession, root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "embed_max_retries", 2)
    monkeypatch.setattr(settings, "embed_batch_max_items", 4)
    flaky = FlakyProvider(RateLimited("slow down"), fail_on={2, 3, 4})
    world = await make_rag_world(session, root, flaky)
    run = await index_once(session, world)
    assert (run.status, run.error) == ("failed", "rate_limited")
    assert flaky.embed_calls == 4  # one good batch, then 1 try + 2 retries
    assert await count_chunks(session, world) == 4

    flaky.fail_on = set()
    run = await index_once(session, world)
    assert run.status == "succeeded"


async def test_second_start_while_active_is_409(session: AsyncSession, world: RagWorld) -> None:
    await start_index(session, world.user_id, world.project_id)
    with pytest.raises(IndexInProgress):
        await start_index(session, world.user_id, world.project_id)


async def test_cancel_between_batches(
    session: AsyncSession, root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "embed_batch_max_items", 4)

    class CancellingProvider(FakeProvider):
        run_id: uuid.UUID | None = None

        async def embed(self, model: str, texts: list[str], **kwargs: object) -> EmbedResult:
            if self.run_id is not None:
                await cancel_run(session, world.user_id, self.run_id)
            return await super().embed(model, texts, **kwargs)  # type: ignore[arg-type]

    provider = CancellingProvider()
    world = await make_rag_world(session, root, provider)
    run = await start_index(session, world.user_id, world.project_id)
    await session.commit()
    provider.run_id = run.id
    from app.modules.rag.service import run_index_job
    from tests.conversation_helpers import session_factory

    await run_index_job(session_factory(session), world.gateway, world.user_id, run.id)
    await session.refresh(run)
    assert run.status == "cancelled"
    assert len([c for c in provider.calls if c.kind == "embed"]) == 1
    assert await count_chunks(session, world) == 4


async def test_cancel_queued_run(session: AsyncSession, world: RagWorld) -> None:
    run = await start_index(session, world.user_id, world.project_id)
    await cancel_run(session, world.user_id, run.id)
    assert run.status == "cancelled" and run.finished_at is not None


async def test_stale_running_job_is_failed_at_startup(
    session: AsyncSession, world: RagWorld
) -> None:
    run = await start_index(session, world.user_id, world.project_id)
    run.status = "running"
    await session.flush()
    assert await recover_interrupted_runs(session) >= 1
    await session.refresh(run)
    assert (run.status, run.error) == ("failed", "interrupted")


async def test_cost_guard(
    session: AsyncSession, world: RagWorld, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "index_cost_limit_usd", 0)
    estimate = await estimate_index(session, world.user_id, world.project_id)
    assert estimate.over_limit and estimate.provider == "google" and estimate.tokens > 0
    with pytest.raises(CostLimitExceeded) as info:
        await start_index(session, world.user_id, world.project_id)
    assert info.value.details["estimate"]["files_to_index"] >= 15
    run = await index_once(session, world, force=True)
    assert run.status == "succeeded" and run.force


async def test_no_source_path(session: AsyncSession, world: RagWorld) -> None:
    from app.modules.projects.repository import ProjectRepository

    await ProjectRepository(session, world.user_id).update(world.project_id, root_path=None)
    with pytest.raises(NoSourcePath):
        await start_index(session, world.user_id, world.project_id)


async def test_embedding_model_change_marks_reindex(session: AsyncSession, world: RagWorld) -> None:
    await index_once(session, world)
    openai = await ModelConfigRepository(session).get_by_litellm_model(
        "openai/text-embedding-3-small"
    )
    assert openai is not None
    await ProviderCredentialRepository(session, world.user_id).add_key(
        provider="openai", api_key="sk-test-openai-0000"
    )
    await UserModelSettingsRepository(session, world.user_id).add(embedding_model_id=openai.id)

    status = await index_status(session, world.user_id, world.project_id)
    assert status.needs_reindex and status.reindex_reasons == ("embedding_model_changed",)
    # Search never compares vectors of two models: the old chunks are ignored.
    result = await search(session, world.gateway, world.user_id, world.project_id, "health")
    assert result.blocks == [] and result.needs_reindex

    run = await index_once(session, world)
    assert run.status == "succeeded"
    assert await count_chunks(session, world, embedding_model=GEMINI) == 0
    status = await index_status(session, world.user_id, world.project_id)
    assert not status.needs_reindex


async def test_skipped_files_are_recorded_with_reasons(
    session: AsyncSession, world: RagWorld, root: Path
) -> None:
    (root / ".env").write_text("TASKBOARD_DEBUG=1\n")
    key = "AKIA" + "QWERTYUIOPASDFGH"  # built at runtime: no secret-shaped text in the repo
    (root / "backend" / "app" / "keys.py").write_text(f"ACCESS = '{key}'\n")
    (root / "logo.png").write_bytes(b"\x89PNG\r\n")
    (root / "debug.log").write_text("x")
    run = await index_once(session, world)
    docs = await documents(session, world)
    assert docs[".env"].skip_reason == "sensitive_name"
    assert docs["backend/app/keys.py"].skip_reason == "possible secret"
    assert docs["logo.png"].skip_reason == "binary"
    assert "debug.log" not in docs  # .gitignore matches are only counted
    assert run.skip_report["gitignored"]["count"] >= 1
    assert run.skip_report["possible secret"]["examples"] == ["backend/app/keys.py"]
    texts = " ".join(embedded_texts(world.fake))
    assert key not in texts and "TASKBOARD_DEBUG=1" not in texts


async def test_logs_hold_no_file_contents(
    session: AsyncSession, world: RagWorld, root: Path, caplog: pytest.LogCaptureFixture
) -> None:
    marker = "zebra_marker_" + uuid.uuid4().hex
    (root / "backend" / "app" / "marker.py").write_text(f"def {marker}():\n    return 1\n")
    caplog.set_level(logging.DEBUG)
    await index_once(session, world)
    await search(session, world.gateway, world.user_id, world.project_id, marker)
    assert caplog.records
    assert marker not in caplog.text
    assert "HASH_ITERATIONS" not in caplog.text


async def test_runs_are_per_user(session: AsyncSession, world: RagWorld, root: Path) -> None:
    run = await index_once(session, world)
    other = await make_rag_world(session, root, name="Other")
    from app.core.errors import NotFound
    from app.modules.rag.service import get_run

    with pytest.raises(NotFound):
        await get_run(session, other.user_id, run.id)
    assert (await session.get(IndexRun, run.id)) is not None
