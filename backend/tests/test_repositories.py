"""Repository tests against the real PostgreSQL test database (`mantle_test`)."""

import uuid
from typing import Any

import pytest
from pydantic import ValidationError
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.repositories import UserRepository
from app.db.models import Base
from app.db.repository import UserScopedRepository
from app.modules.conversations.repository import (
    ConversationSummaryRepository,
    MessageRepository,
)
from app.modules.llm.repository import (
    ModelConfigRepository,
    UsageRecordRepository,
)
from app.modules.projects.repository import ProjectRepository
from app.modules.rag.repository import ChunkRepository
from tests.graph import (
    ALL_USER_REPOSITORIES,
    PROJECT_SCOPED,
    USER_SCOPED,
    Graph,
    build_graph,
    make_models,
    make_user,
)

pytestmark = pytest.mark.db


@pytest.fixture
async def models(session: AsyncSession) -> tuple[uuid.UUID, uuid.UUID]:
    return await make_models(session)


@pytest.fixture
async def graph_a(session: AsyncSession, models: tuple[uuid.UUID, uuid.UUID]) -> Graph:
    user_id = await make_user(session, "Alice")
    return await build_graph(session, user_id, *models)


@pytest.fixture
async def graph_b(session: AsyncSession, models: tuple[uuid.UUID, uuid.UUID]) -> Graph:
    user_id = await make_user(session, "Bob")
    return await build_graph(session, user_id, *models)


def repo_id(repo: type) -> str:
    return repo.__name__


def test_every_user_table_has_a_repository_under_test() -> None:
    user_tables = {t.name for t in Base.metadata.tables.values() if "user_id" in t.columns}
    tested = {repo.model.__tablename__ for repo in ALL_USER_REPOSITORIES}
    assert tested == user_tables
    assert len(user_tables) == 20


@pytest.mark.parametrize("repo", ALL_USER_REPOSITORIES, ids=repo_id)
async def test_create_and_read(
    session: AsyncSession, graph_a: Graph, repo: type[UserScopedRepository[Any]]
) -> None:
    row_id = graph_a.id(repo)
    session.expunge_all()  # force a real read from the database

    found = await repo(session, graph_a.user_id).get(row_id)
    assert found is not None
    assert found.id == row_id
    assert found.user_id == graph_a.user_id
    assert found.created_at.tzinfo is not None
    assert found.updated_at.tzinfo is not None
    assert row_id in [r.id for r in await repo(session, graph_a.user_id).list()]


async def test_user_and_model_config_repositories(session: AsyncSession) -> None:
    user_id = await make_user(session, "Carol")
    chat_id, _ = await make_models(session)
    session.expunge_all()

    user = await UserRepository(session).get(user_id)
    assert user is not None and user.display_name == "Carol"
    model = await ModelConfigRepository(session).get(chat_id)
    assert model is not None and model.kind == "chat"
    assert await ModelConfigRepository(session).get_by_litellm_model(model.litellm_model)

    updated = await ModelConfigRepository(session).update(chat_id, enabled=False)
    assert updated is not None and updated.enabled is False


@pytest.mark.parametrize("repo", ALL_USER_REPOSITORIES, ids=repo_id)
async def test_user_isolation(
    session: AsyncSession, graph_a: Graph, graph_b: Graph, repo: type[UserScopedRepository[Any]]
) -> None:
    a_row_id = graph_a.id(repo)
    as_b = repo(session, graph_b.user_id)

    assert await as_b.get(a_row_id) is None
    assert a_row_id not in [r.id for r in await as_b.list()]
    assert await as_b.list(id=a_row_id) == []
    assert await as_b.update(a_row_id) is None
    assert await as_b.delete(a_row_id) is False

    # Alice's row is still there.
    assert await repo(session, graph_a.user_id).get(a_row_id) is not None


async def test_repository_refuses_to_set_user_id(session: AsyncSession, graph_a: Graph) -> None:
    repo = ProjectRepository(session, graph_a.user_id)
    with pytest.raises(ValueError, match="user_id"):
        await repo.add(name="x", user_id=uuid.uuid4())
    with pytest.raises(ValueError, match="user_id"):
        await repo.update(graph_a.id(ProjectRepository), user_id=uuid.uuid4())


async def test_deleting_a_project_removes_its_rows(
    session: AsyncSession, graph_a: Graph, graph_b: Graph
) -> None:
    assert await ProjectRepository(session, graph_a.user_id).delete(graph_a.id(ProjectRepository))
    session.expunge_all()

    for repo in PROJECT_SCOPED:
        model = repo.model
        gone = await session.scalar(select(model).where(model.id == graph_a.id(repo)))
        assert gone is None, f"{model.__tablename__} row survived the project delete"

    # User-level rows stay. Usage history is kept, with its project links cleared.
    for repo in USER_SCOPED:
        assert await repo(session, graph_a.user_id).get(graph_a.id(repo)) is not None
    usage = await UsageRecordRepository(session, graph_a.user_id).get(
        graph_a.id(UsageRecordRepository)
    )
    assert usage is not None
    assert (usage.project_id, usage.conversation_id, usage.message_id, usage.agent_run_id) == (
        None,
        None,
        None,
        None,
    )

    # Bob's project is untouched.
    for repo in PROJECT_SCOPED:
        assert await repo(session, graph_b.user_id).get(graph_b.id(repo)) is not None


async def test_message_content_is_provider_neutral(session: AsyncSession, graph_a: Graph) -> None:
    conversation_id = graph_a.rows[MessageRepository].conversation_id
    repo = MessageRepository(session, graph_a.user_id)
    parts = [
        {"type": "text", "text": "Let me check."},
        {"type": "tool_call", "id": "call_1", "name": "search", "arguments": {"q": "x"}},
    ]
    message = await repo.add(conversation_id=conversation_id, role="assistant", content=parts)
    result = await repo.add(
        conversation_id=conversation_id,
        role="tool",
        content=[{"type": "tool_result", "tool_call_id": "call_1", "content": "found"}],
    )
    session.expunge_all()

    stored = await repo.get(message.id)
    assert stored is not None and stored.content == parts
    stored_result = await repo.get(result.id)
    assert stored_result is not None
    assert stored_result.content[0]["is_error"] is False

    with pytest.raises(ValidationError):
        await repo.add(conversation_id=conversation_id, role="user", content=[{"type": "image"}])


async def test_latest_summary(session: AsyncSession, graph_a: Graph) -> None:
    first = graph_a.rows[ConversationSummaryRepository]
    repo = ConversationSummaryRepository(session, graph_a.user_id)
    # One test transaction means one now(); age the first row so "newest" is well defined.
    await session.execute(
        text("UPDATE conversation_summaries SET created_at = now() - interval '1 minute' "
             "WHERE id = :id"),
        {"id": first.id},
    )  # fmt: skip
    newer = await repo.add(
        conversation_id=first.conversation_id,
        summary="Newer.",
        up_to_message_id=first.up_to_message_id,
        model_id=first.model_id,
        built_at="switch",
    )
    latest = await repo.latest(first.conversation_id)
    assert latest is not None and latest.id == newer.id


async def test_chunk_embedding_round_trip(session: AsyncSession, graph_a: Graph) -> None:
    chunk_id = graph_a.id(ChunkRepository)
    session.expunge_all()
    chunk = await ChunkRepository(session, graph_a.user_id).get(chunk_id)
    assert chunk is not None
    assert len(chunk.embedding) == chunk.embedding_dimensions
    assert chunk.embedding_model == "openai/test-embed"
