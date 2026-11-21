"""Background jobs and their races, on separate database connections (committed data, cleaned
up after each test). A blocking fake provider holds a model call open, so a run is really in
flight while another request arrives. No keys, no network."""

import asyncio
import json
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.config import settings
from app.core.models import User
from app.modules.llm.backend import ChatMessages, StreamItem
from app.modules.llm.fake import FakeProvider
from app.modules.llm.gateway import Gateway
from app.modules.llm.models import ModelConfig
from app.modules.llm.repository import ProviderCredentialRepository, UserModelSettingsRepository
from app.modules.projects.repository import ProjectRepository
from app.modules.rag.models import IndexRun
from app.modules.workflow.models import AgentRun, RunStatus, RunType
from tests.agent_helpers import gap_report, review
from tests.committed_helpers import Committed, committed_world
from tests.rag_helpers import copy_fixture, fast_settings

pytestmark = pytest.mark.db

WAIT = 10  # seconds; a step that should be instant fails the test long before this


class BlockingProvider(FakeProvider):
    """Every chat call waits for `release` after telling `entered`, then answers `reply`."""

    def __init__(self, reply: dict[str, Any]) -> None:
        super().__init__(default_reply=json.dumps(reply))
        self.entered = asyncio.Event()
        self.release = asyncio.Event()

    async def stream_chat(
        self, model: str, messages: ChatMessages, *, api_key: str, max_tokens: int | None
    ) -> AsyncIterator[StreamItem]:
        self.entered.set()
        await self.release.wait()
        async for item in super().stream_chat(model, messages, api_key=api_key,
                                               max_tokens=max_tokens):  # fmt: skip
            yield item


def runs_url(world: Committed) -> str:
    return f"/api/v1/projects/{world.project_id}/agent-runs"


def review_body(world: Committed) -> dict[str, str]:
    return {"run_type": "review", "model_id": str(world.model_id)}


async def active_runs(world: Committed) -> int:
    async with world.session() as s:
        return int(await s.scalar(select(func.count()).select_from(AgentRun).where(
            AgentRun.project_id == world.project_id,
            AgentRun.status.in_([RunStatus.QUEUED, RunStatus.RUNNING]),
        )) or 0)  # fmt: skip


async def test_a_run_start_during_a_gap_finder_call_answers_409_at_once(
    engine: AsyncEngine,
) -> None:
    """Audit A-008: the gap finder's running row must be visible before its model call, so a
    start in another request gets 409 instead of waiting on the unique index."""
    async with committed_world(engine) as world:
        provider = BlockingProvider(gap_report())
        async with world.client(Gateway(provider)) as c:
            gap = asyncio.create_task(c.post(
                f"/api/v1/projects/{world.project_id}/gap-finder",
                json={"model_id": str(world.model_id)}))  # fmt: skip
            await asyncio.wait_for(provider.entered.wait(), WAIT)
            try:
                start = await asyncio.wait_for(c.post(runs_url(world), json=review_body(world)), 5)
            finally:
                provider.release.set()
            assert start.status_code == 409, start.text
            assert start.json()["error"]["code"] == "agent_run_in_progress"
            done = await asyncio.wait_for(gap, WAIT)
        assert done.status_code == 200, done.text
        assert done.json()["status"] == "completed"
        assert await active_runs(world) == 0


async def test_a_gap_finder_that_dies_mid_call_leaves_no_running_row(engine: AsyncEngine) -> None:
    """Once the running row is committed early, a gap finder whose task is cancelled (the
    server stopping) must still end it, or the project is blocked until a restart. Run on
    its own connection; cancelling an httpx test client would not reach the app's task."""
    from app.modules.workflow.gap_finder import run_gap_finder

    async with committed_world(engine) as world:
        provider = BlockingProvider(gap_report())
        async with world.session() as s:
            task = asyncio.create_task(
                run_gap_finder(
                    s, Gateway(provider), world.user_id, world.project_id, world.model_id
                )  # fmt: skip
            )
            await asyncio.wait_for(provider.entered.wait(), WAIT)
            assert await active_runs(world) == 1  # committed before the model call
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        assert await active_runs(world) == 0
        async with world.session() as s:
            [run] = list(await s.scalars(select(AgentRun).where(
                AgentRun.project_id == world.project_id)))  # fmt: skip
        assert (run.status, run.error) == (RunStatus.FAILED, "interrupted")


async def test_two_starts_at_once_give_one_run(engine: AsyncEngine) -> None:
    async with committed_world(engine) as world:
        provider = BlockingProvider(review())
        async with world.client(Gateway(provider)) as c:
            first = asyncio.create_task(c.post(runs_url(world), json=review_body(world)))
            second = asyncio.create_task(c.post(runs_url(world), json=review_body(world)))
            # One of them is now in its job (blocked in the model call); the other answered.
            done, _ = await asyncio.wait({first, second}, timeout=WAIT,
                                         return_when=asyncio.FIRST_COMPLETED)  # fmt: skip
            assert len(done) == 1
            assert await active_runs(world) == 1
            provider.release.set()
            answers = sorted([(await first).status_code, (await second).status_code])
        assert answers == [202, 409]
        assert await active_runs(world) == 0


async def test_a_cancel_during_the_last_step_wins(engine: AsyncEngine) -> None:
    """The Reviewer (the only step of a review run) is in its model call when the cancel
    commits on another connection: the run ends cancelled, not completed."""
    async with committed_world(engine) as world:
        provider = BlockingProvider(review())
        async with world.client(Gateway(provider)) as c:
            start = asyncio.create_task(c.post(runs_url(world), json=review_body(world)))
            await asyncio.wait_for(provider.entered.wait(), WAIT)
            async with world.session() as s:
                run_id = await s.scalar(select(AgentRun.id).where(
                    AgentRun.project_id == world.project_id))  # fmt: skip
            cancel = await c.post(f"/api/v1/agent-runs/{run_id}/cancel", json={})
            assert cancel.status_code == 200 and cancel.json()["status"] == "running"
            provider.release.set()
            assert (await asyncio.wait_for(start, WAIT)).status_code == 202
        assert run_id is not None
        final = await world.run_status(run_id)
        assert final.status == RunStatus.CANCELLED and final.finished_at is not None


async def test_start_during_a_cancel_never_makes_two_active_runs(engine: AsyncEngine) -> None:
    async with committed_world(engine) as world:
        run_id = await world.add_run(RunStatus.QUEUED, RunType.REVIEW)
        async with world.client() as c:
            cancel, start = await asyncio.gather(
                c.post(f"/api/v1/agent-runs/{run_id}/cancel", json={}),
                c.post(runs_url(world), json=review_body(world)),
            )
        assert cancel.status_code == 200 and cancel.json()["status"] == "cancelled"
        assert start.status_code in (202, 409), start.text  # 409 if it saw the queued run
        assert await active_runs(world) == 0
        assert (await world.run_status(run_id)).status == RunStatus.CANCELLED


async def test_a_gap_finder_crash_ends_its_run(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.modules.workflow import gap_finder

    async def crash(*_: object, **__: object) -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr(gap_finder, "run_step", crash)
    async with committed_world(engine) as world:
        async with world.client() as c:
            r = await c.post(f"/api/v1/projects/{world.project_id}/gap-finder",
                             json={"model_id": str(world.model_id)})  # fmt: skip
        assert r.status_code == 500 and r.json()["error"]["code"] == "internal_error"
        assert await active_runs(world) == 0
        async with world.session() as s:
            [run] = list(await s.scalars(select(AgentRun).where(
                AgentRun.project_id == world.project_id)))  # fmt: skip
        assert (run.status, run.error) == (RunStatus.FAILED, "internal_error")


# ---- index runs and the rolling summary ----------------------------------------------------


@asynccontextmanager
async def committed_index_world(engine: AsyncEngine, root: Path) -> AsyncIterator[Committed]:
    """A user with a project folder, a google key and one embedding model, committed. The
    full catalog is not seeded here: committed catalog rows would leak into other tests."""
    async with AsyncSession(engine, expire_on_commit=False) as s:
        user = User(display_name="Index race")
        s.add(user)
        model = ModelConfig(
            provider="google", litellm_model=f"fake/embed-{uuid.uuid4().hex[:6]}",
            display_name="Fake embed", kind="embedding", context_window=8_000,
            embedding_dimensions=settings.embedding_dimensions, supports_tools=False,
            input_cost_per_mtok=Decimal("0.01"), output_cost_per_mtok=Decimal("0"),
        )  # fmt: skip
        s.add(model)
        await s.flush()
        project = await ProjectRepository(s, user.id).add(name="Index", root_path=str(root))
        await ProviderCredentialRepository(s, user.id).add_key(
            provider="google", api_key="sk-test-index-race-0000"
        )
        await UserModelSettingsRepository(s, user.id).add(embedding_model_id=model.id)
        await s.commit()
        world = Committed(engine, user.id, project.id, model.id)
    try:
        yield world
    finally:
        async with AsyncSession(engine) as s:
            await s.execute(delete(User).where(User.id == world.user_id))
            await s.execute(delete(ModelConfig).where(ModelConfig.id == world.model_id))
            await s.commit()


async def test_two_index_starts_at_once_give_one_run(
    engine: AsyncEngine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fast_settings(monkeypatch)
    root = copy_fixture(tmp_path).resolve()
    async with committed_index_world(engine, root) as world:
        async with world.client() as c:
            url = f"/api/v1/projects/{world.project_id}/index"
            first, second = await asyncio.gather(
                c.post(url, json={"force": True}), c.post(url, json={"force": True})
            )
        codes = sorted([first.status_code, second.status_code])
        assert codes == [202, 409], (first.text, second.text)
        loser = first if first.status_code == 409 else second
        assert loser.json()["error"]["code"] == "index_in_progress"
        async with world.session() as s:
            runs = list(await s.scalars(select(IndexRun).where(
                IndexRun.project_id == world.project_id)))  # fmt: skip
        assert len(runs) == 1 and runs[0].status == "succeeded"


async def test_two_summary_jobs_at_once_write_one_summary(
    engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.modules.conversations.repository import ConversationSummaryRepository
    from app.modules.conversations.summary import run_rolling_summary
    from tests.conversation_helpers import add_messages, make_world, turns

    monkeypatch.setattr(settings, "summary_trigger_tokens", 500)
    monkeypatch.setattr(settings, "context_keep_recent_turns", 1)
    async with AsyncSession(engine, expire_on_commit=False) as s:
        world = await make_world(s, "Summary race")
        await add_messages(s, world, turns(1, 5))
        await s.commit()
    provider = BlockingProvider({})
    provider.set_reply(world.litellm("small"), "summary text")

    @asynccontextmanager
    async def own_session() -> AsyncIterator[AsyncSession]:
        async with AsyncSession(engine, expire_on_commit=False) as session:
            yield session

    try:
        first = asyncio.create_task(run_rolling_summary(
            own_session, Gateway(provider), world.user_id, world.conversation_id))  # fmt: skip
        await asyncio.wait_for(provider.entered.wait(), WAIT)
        second = await asyncio.wait_for(run_rolling_summary(
            own_session, Gateway(provider), world.user_id, world.conversation_id), 5)  # fmt: skip
        provider.release.set()
        assert second == "locked"
        assert await asyncio.wait_for(first, WAIT) == "done"
        async with own_session() as s:
            rows = await ConversationSummaryRepository(s, world.user_id).list(
                conversation_id=world.conversation_id)  # fmt: skip
        assert len(rows) == 1
    finally:
        provider.release.set()
        async with AsyncSession(engine) as s:
            await s.execute(delete(User).where(User.id == world.user_id))
            await s.execute(delete(ModelConfig).where(
                ModelConfig.id.in_([m for m, _ in world.models.values()])))  # fmt: skip
            await s.commit()
