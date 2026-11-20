"""Committed test data for concurrency tests.

Races need two real connections, and a second connection can't see the rolled-back test
session's data. So these helpers commit to `mantle_test` and delete everything afterwards
(deleting the user cascades to its projects, memory and runs)."""

import uuid
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import httpx
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.api.deps import get_current_user_id, get_db, get_session_factory
from app.core.models import User
from app.main import app
from app.modules.llm.fake import FakeProvider
from app.modules.llm.gateway import Gateway
from app.modules.llm.models import ModelConfig
from app.modules.llm.repository import ProviderCredentialRepository
from app.modules.llm.service import get_gateway
from app.modules.projects.repository import ProjectRepository
from app.modules.workflow.models import AgentRun, RunStatus, RunType
from tests.agent_helpers import plan, review


@dataclass
class Committed:
    engine: AsyncEngine
    user_id: uuid.UUID
    project_id: uuid.UUID
    model_id: uuid.UUID

    def session(self) -> AsyncSession:
        return AsyncSession(self.engine, expire_on_commit=False)

    def factory(self) -> Callable[[], AbstractAsyncContextManager[AsyncSession]]:
        @asynccontextmanager
        async def make() -> AsyncIterator[AsyncSession]:
            async with self.session() as s:
                yield s

        return make

    async def add_run(self, status: RunStatus, run_type: RunType = RunType.PLAN) -> uuid.UUID:
        async with self.session() as s:
            run = AgentRun(
                user_id=self.user_id, project_id=self.project_id, run_type=run_type,
                status=status, model_id=self.model_id, prompt_version="planner_v1,reviewer_v1",
                stage_id="requirements", result={"plan": plan(), "review": review()},
            )  # fmt: skip
            s.add(run)
            await s.commit()
            return run.id

    async def run_status(self, run_id: uuid.UUID) -> AgentRun:
        async with self.session() as s:
            found = await s.get(AgentRun, run_id)
            assert found is not None
            return found

    @asynccontextmanager
    async def client(self, gateway: Gateway | None = None) -> AsyncIterator[httpx.AsyncClient]:
        """An API client where every request gets its own connection. Model calls go to
        `gateway` (a fake provider by default), never to a real one."""
        fake = gateway or Gateway(FakeProvider())

        async def own_session() -> AsyncIterator[AsyncSession]:
            async with self.session() as s:
                yield s

        app.dependency_overrides[get_db] = own_session
        app.dependency_overrides[get_session_factory] = self.factory
        app.dependency_overrides[get_current_user_id] = lambda: self.user_id
        app.dependency_overrides[get_gateway] = lambda: fake
        try:
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://localhost") as c:
                yield c
        finally:
            app.dependency_overrides.clear()


@asynccontextmanager
async def committed_world(engine: AsyncEngine, **model: Any) -> AsyncIterator[Committed]:
    async with AsyncSession(engine, expire_on_commit=False) as s:
        user = User(display_name="Committed")
        s.add(user)
        row = ModelConfig(
            provider="openai", litellm_model=f"fake/committed-{uuid.uuid4().hex[:6]}",
            display_name="Fake committed", kind="chat", context_window=100_000,
            max_output_tokens=4_000, supports_tools=False,
            input_cost_per_mtok=Decimal("1"), output_cost_per_mtok=Decimal("2"), **model,
        )  # fmt: skip
        s.add(row)
        await s.flush()
        project = await ProjectRepository(s, user.id).add(name="Committed")
        await ProviderCredentialRepository(s, user.id).add_key(
            provider="openai", api_key="sk-test-committed-0000"
        )
        await s.commit()
        world = Committed(engine, user.id, project.id, row.id)
    try:
        yield world
    finally:
        async with AsyncSession(engine) as s:
            await s.execute(delete(User).where(User.id == world.user_id))
            await s.execute(delete(ModelConfig).where(ModelConfig.id == world.model_id))
            await s.commit()
