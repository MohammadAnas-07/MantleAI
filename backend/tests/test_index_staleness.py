"""An index run left "running" by a job that died while the server stayed up can be cancelled
once it has been silent for INDEX_RUN_STALE_SECONDS (test database, FakeProvider)."""

import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.modules.llm.backend import EmbedResult
from app.modules.llm.fake import FakeProvider
from app.modules.rag.models import IndexRun
from app.modules.rag.service import cancel_run, run_index_job, start_index
from tests.conversation_helpers import session_factory
from tests.rag_helpers import copy_fixture, fast_settings, make_rag_world

pytestmark = pytest.mark.db


@pytest.fixture(autouse=True)
def _fast(monkeypatch: pytest.MonkeyPatch) -> None:
    fast_settings(monkeypatch)


async def running_run(session: AsyncSession, tmp_path: Path, silent_for: timedelta) -> IndexRun:
    world = await make_rag_world(session, copy_fixture(tmp_path), name="Stale")
    run = await start_index(session, world.user_id, world.project_id)
    run.status, run.started_at = "running", datetime.now(UTC) - silent_for
    await session.flush()
    await session.execute(update(IndexRun).where(IndexRun.id == run.id).values(
        updated_at=datetime.now(UTC) - silent_for))  # fmt: skip
    return run


async def test_a_silent_running_run_is_cancelled_at_once(
    session: AsyncSession, tmp_path: Path
) -> None:
    run = await running_run(session, tmp_path, timedelta(hours=2))
    await cancel_run(session, run.user_id, run.id)
    await session.refresh(run)
    assert run.status == "cancelled" and run.finished_at is not None
    again = await start_index(session, run.user_id, run.project_id)  # no longer blocked
    assert again.status == "queued"


async def test_a_recently_active_run_only_gets_the_request(
    session: AsyncSession, tmp_path: Path
) -> None:
    run = await running_run(session, tmp_path, timedelta(seconds=30))
    await cancel_run(session, run.user_id, run.id)
    await session.refresh(run)
    assert run.status == "running" and run.cancel_requested_at is not None


async def test_a_job_that_was_still_alive_does_not_undo_the_cancel(
    session: AsyncSession, tmp_path: Path
) -> None:
    """If the threshold was wrong and the job is alive, its end doesn't turn the cancelled
    run back into succeeded."""

    class StaleCancelProvider(FakeProvider):
        run_id: uuid.UUID | None = None

        async def embed(self, model: str, texts: list[str], **kwargs: object) -> EmbedResult:
            if self.run_id is not None:
                old = datetime.now(UTC) - timedelta(seconds=settings.index_run_stale_seconds + 60)
                await session.execute(update(IndexRun).where(IndexRun.id == self.run_id)
                                      .values(updated_at=old))  # fmt: skip
                await cancel_run(session, user_id, self.run_id)
                self.run_id = None
            return await super().embed(model, texts, **kwargs)  # type: ignore[arg-type]

    provider = StaleCancelProvider()
    world = await make_rag_world(session, copy_fixture(tmp_path), provider, name="Alive")
    user_id = world.user_id
    run = await start_index(session, world.user_id, world.project_id)
    await session.commit()
    provider.run_id = run.id
    await run_index_job(session_factory(session), world.gateway, world.user_id, run.id)
    await session.refresh(run)
    assert run.status == "cancelled"
