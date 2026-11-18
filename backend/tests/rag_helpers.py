"""Shared setup for rag tests: a user with a Google key, a project pointing at a folder, a
FakeProvider gateway, and a helper that runs one index job to the end."""

import shutil
import uuid
from dataclasses import dataclass
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.modules.llm.catalog import seed_default_models
from app.modules.llm.fake import FakeProvider
from app.modules.llm.gateway import Gateway
from app.modules.llm.repository import ProviderCredentialRepository
from app.modules.projects.repository import ProjectRepository
from app.modules.rag import indexer
from app.modules.rag.models import Chunk, Document, IndexRun
from app.modules.rag.service import run_index_job, start_index
from tests.conversation_helpers import session_factory
from tests.graph import make_user

GEMINI = "gemini/gemini-embedding-001"
FIXTURE = Path(__file__).parent / "fixtures" / "sample_project"


@dataclass
class RagWorld:
    user_id: uuid.UUID
    project_id: uuid.UUID
    root: Path
    fake: FakeProvider
    gateway: Gateway


def fast_settings(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """No pauses between batches; backoff sleeps are recorded instead of waited."""
    sleeps: list[float] = []

    async def no_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    monkeypatch.setattr(indexer, "_sleep", no_sleep)
    monkeypatch.setattr(settings, "embed_batch_delay_seconds", 0.0)
    return sleeps


async def make_rag_world(
    session: AsyncSession, root: Path, fake: FakeProvider | None = None, name: str = "Rag"
) -> RagWorld:
    await seed_default_models(session)
    user_id = await make_user(session, name)
    await ProviderCredentialRepository(session, user_id).add_key(
        provider="google", api_key="test-google-key-0000"
    )
    project = await ProjectRepository(session, user_id).add(
        name="Sample", root_path=str(root.resolve())
    )
    fake = fake or FakeProvider()
    return RagWorld(user_id, project.id, root.resolve(), fake, Gateway(fake))


def copy_fixture(tmp_path: Path) -> Path:
    target = tmp_path / "sample project"
    shutil.copytree(FIXTURE, target)
    return target


async def index_once(session: AsyncSession, world: RagWorld, *, force: bool = False) -> IndexRun:
    run = await start_index(session, world.user_id, world.project_id, force=force)
    await session.commit()
    await run_index_job(session_factory(session), world.gateway, world.user_id, run.id)
    await session.refresh(run)
    return run


def embedded_texts(fake: FakeProvider) -> list[str]:
    return [t for call in fake.calls if call.kind == "embed" for t in call.texts]


async def count_chunks(session: AsyncSession, world: RagWorld, **filters: object) -> int:
    stmt = select(func.count()).select_from(Chunk).where(Chunk.project_id == world.project_id)
    for name, value in filters.items():
        stmt = stmt.where(getattr(Chunk, name) == value)
    return int(await session.scalar(stmt) or 0)


async def documents(session: AsyncSession, world: RagWorld) -> dict[str, Document]:
    rows = await session.scalars(select(Document).where(Document.project_id == world.project_id))
    return {d.path: d for d in rows}
