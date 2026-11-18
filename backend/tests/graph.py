"""Builds one row in every table for a user, through the repositories. Used by the DB tests."""

import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.repositories import AuditEventRepository, UserRepository
from app.db.repository import UserScopedRepository
from app.modules.conversations.repository import (
    ContextHandoffRepository,
    ConversationRepository,
    ConversationSummaryRepository,
    MessageContextRepository,
    MessageRepository,
)
from app.modules.llm.repository import (
    ModelConfigRepository,
    ProviderCredentialRepository,
    UsageRecordRepository,
    UserModelSettingsRepository,
)
from app.modules.projects.repository import MemoryItemRepository, ProjectRepository
from app.modules.rag.repository import (
    ChunkRepository,
    DocumentRepository,
    IndexRunRepository,
    ProjectProfileRepository,
)
from app.modules.teaching.repository import ConceptSuggestionRepository, TeachingNoteRepository
from app.modules.workflow.repository import (
    AgentRunRepository,
    StageStateRepository,
    WorkflowRunRepository,
)

FAKE_API_KEY = "test-not-a-real-key-1234"


async def make_user(session: AsyncSession, name: str) -> uuid.UUID:
    user = await UserRepository(session).add(display_name=name)
    return user.id


async def make_models(session: AsyncSession) -> tuple[uuid.UUID, uuid.UUID]:
    repo = ModelConfigRepository(session)
    suffix = uuid.uuid4().hex[:8]
    chat = await repo.add(
        provider="openai",
        litellm_model=f"openai/test-chat-{suffix}",
        display_name="Test chat",
        kind="chat",
        context_window=128_000,
        max_output_tokens=4_096,
    )
    embed = await repo.add(
        provider="openai",
        litellm_model=f"openai/test-embed-{suffix}",
        display_name="Test embed",
        kind="embedding",
        context_window=8_191,
        embedding_dimensions=settings.embedding_dimensions,
    )
    return chat.id, embed.id


@dataclass
class Graph:
    """One row per user-data table, keyed by repository class."""

    user_id: uuid.UUID
    rows: dict[type[UserScopedRepository[Any]], Any] = field(default_factory=dict)

    def id(self, repo: type[UserScopedRepository[Any]]) -> uuid.UUID:
        return self.rows[repo].id


async def build_graph(
    session: AsyncSession, user_id: uuid.UUID, chat_id: uuid.UUID, embed_id: uuid.UUID
) -> Graph:
    g = Graph(user_id=user_id)

    async def add(repo: type[UserScopedRepository[Any]], **values: Any) -> Any:
        row = await repo(session, user_id).add(**values)
        g.rows[repo] = row
        return row

    g.rows[ProviderCredentialRepository] = await ProviderCredentialRepository(
        session, user_id
    ).add_key(provider="openai", api_key=FAKE_API_KEY, label="test")
    await add(UserModelSettingsRepository, utility_model_id=chat_id, embedding_model_id=embed_id)
    await add(AuditEventRepository, event_type="credential.added", details={"provider": "openai"})

    project = await add(ProjectRepository, name="Demo", root_path="C:/demo")
    conversation = await add(
        ConversationRepository, project_id=project.id, title="Chat", current_model_id=chat_id
    )
    message = await add(
        MessageRepository,
        conversation_id=conversation.id,
        sequence=1,
        role="assistant",
        content=[{"type": "text", "text": "hello"}],
        model_id=chat_id,
        token_count=1,
        input_tokens=10,
        output_tokens=1,
    )
    summary = await add(
        ConversationSummaryRepository,
        conversation_id=conversation.id,
        from_sequence=1,
        to_sequence=1,
        summary="Goals: demo.",
        up_to_message_id=message.id,
        model_id=chat_id,
        built_at="background",
        token_count=3,
    )
    await add(
        ContextHandoffRepository,
        conversation_id=conversation.id,
        from_model_id=chat_id,
        to_model_id=chat_id,
        reason="user_choice",
        conversation_summary_id=summary.id,
        first_raw_message_id=message.id,
    )
    await add(
        MessageContextRepository,
        message_id=message.id,
        source_type="summary",
        source_id=summary.id,
        rank=1,
    )

    run = await add(IndexRunRepository, project_id=project.id, embedding_model_id=embed_id)
    document = await add(
        DocumentRepository,
        project_id=project.id,
        path="app/main.py",
        content_hash="0" * 64,
        size_bytes=120,
        language="python",
        last_index_run_id=run.id,
    )
    await add(
        ChunkRepository,
        document_id=document.id,
        project_id=project.id,
        ordinal=0,
        text="print('hi')",
        start_line=1,
        end_line=1,
        token_count=4,
        embedding=[0.1] * settings.embedding_dimensions,
        embedding_model="openai/test-embed",
        embedding_dimensions=settings.embedding_dimensions,
    )
    await add(
        ProjectProfileRepository,
        project_id=project.id,
        languages={"python": 1},
        dependencies=["fastapi"],
        markers=["tests"],
        index_run_id=run.id,
    )

    workflow = await add(WorkflowRunRepository, project_id=project.id)
    stage = await add(
        StageStateRepository, workflow_run_id=workflow.id, stage_key="requirements", position=0
    )
    agent_run = await add(
        AgentRunRepository, stage_state_id=stage.id, agent="planner", model_id=chat_id
    )

    await add(
        MemoryItemRepository,
        project_id=project.id,
        kind="decision",
        title="Use PostgreSQL",
        source="agent",
        source_message_id=message.id,
        source_agent_run_id=agent_run.id,
    )
    note = await add(
        TeachingNoteRepository,
        project_id=project.id,
        concept="Database indexing",
        what="w",
        why_here="y",
        how="h",
        source_message_id=message.id,
        model_id=chat_id,
    )
    await add(
        ConceptSuggestionRepository,
        project_id=project.id,
        rule_id="database-indexing",
        concept="Database indexing",
        reason="dependency: sqlalchemy",
        teaching_note_id=note.id,
    )
    await add(
        UsageRecordRepository,
        model_id=chat_id,
        purpose="rolling_summary",
        trigger="background",
        project_id=project.id,
        conversation_id=conversation.id,
        message_id=message.id,
        agent_run_id=agent_run.id,
        input_tokens=10,
        output_tokens=1,
        status="success",
    )
    return g


# Rows that belong to the project and must disappear when it is deleted.
PROJECT_SCOPED = [
    ProjectRepository,
    MemoryItemRepository,
    ConversationRepository,
    MessageRepository,
    ConversationSummaryRepository,
    ContextHandoffRepository,
    MessageContextRepository,
    IndexRunRepository,
    DocumentRepository,
    ChunkRepository,
    ProjectProfileRepository,
    WorkflowRunRepository,
    StageStateRepository,
    AgentRunRepository,
    TeachingNoteRepository,
    ConceptSuggestionRepository,
]

# Rows that belong to the user and survive a project delete.
USER_SCOPED = [
    ProviderCredentialRepository,
    UserModelSettingsRepository,
    AuditEventRepository,
    UsageRecordRepository,
]

ALL_USER_REPOSITORIES = PROJECT_SCOPED + USER_SCOPED
