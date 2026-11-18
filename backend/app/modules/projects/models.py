"""Tables owned by the projects module: Project, MemoryItem and MemoryDependency."""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import CheckConstraint, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import UserOwnedEntity, fk, str_enum


class MemoryItemKind(StrEnum):
    REQUIREMENT = "requirement"
    DECISION = "decision"
    TASK = "task"


class MemoryItemStatus(StrEnum):
    """All statuses in one column. Which ones a kind may use is in `STATUSES_BY_KIND`."""

    # decisions
    PROPOSED = "proposed"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    DEPRECATED = "deprecated"
    SUPERSEDED = "superseded"
    # tasks
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    BLOCKED = "blocked"
    # requirements
    DRAFT = "draft"
    APPROVED = "approved"
    DROPPED = "dropped"


class MemoryItemPriority(StrEnum):
    """Requirements use must/should/could; tasks use low/medium/high; decisions use none."""

    MUST = "must"
    SHOULD = "should"
    COULD = "could"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


S, P = MemoryItemStatus, MemoryItemPriority

STATUSES_BY_KIND: dict[MemoryItemKind, tuple[MemoryItemStatus, ...]] = {
    MemoryItemKind.DECISION: (S.PROPOSED, S.ACCEPTED, S.REJECTED, S.DEPRECATED, S.SUPERSEDED),
    MemoryItemKind.TASK: (S.TODO, S.IN_PROGRESS, S.DONE, S.BLOCKED),
    MemoryItemKind.REQUIREMENT: (S.DRAFT, S.APPROVED, S.DROPPED),
}
DEFAULT_STATUS: dict[MemoryItemKind, MemoryItemStatus] = {
    MemoryItemKind.DECISION: S.ACCEPTED,
    MemoryItemKind.TASK: S.TODO,
    MemoryItemKind.REQUIREMENT: S.DRAFT,
}
PRIORITIES_BY_KIND: dict[MemoryItemKind, tuple[MemoryItemPriority, ...]] = {
    MemoryItemKind.DECISION: (),
    MemoryItemKind.TASK: (P.HIGH, P.MEDIUM, P.LOW),
    MemoryItemKind.REQUIREMENT: (P.MUST, P.SHOULD, P.COULD),
}


class MemoryItemSource(StrEnum):
    USER = "user"
    CHAT = "chat"
    AGENT = "agent"


class Project(UserOwnedEntity):
    __tablename__ = "projects"

    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    root_path: Mapped[str | None] = mapped_column(Text)
    default_model_id: Mapped[uuid.UUID | None] = mapped_column(
        fk("model_configs", ondelete="SET NULL"), index=True
    )
    archived_at: Mapped[datetime | None]


class MemoryItem(UserOwnedEntity):
    """Requirements, decisions and tasks in one table.

    For a decision, `body` is what was decided; `why`, `alternatives` and `decided_at` are
    decision-only. A superseded decision points at the decision that replaced it.
    """

    __tablename__ = "memory_items"

    project_id: Mapped[uuid.UUID] = mapped_column(fk("projects", ondelete="CASCADE"), index=True)
    kind: Mapped[MemoryItemKind] = mapped_column(str_enum(MemoryItemKind))
    title: Mapped[str] = mapped_column(String(300))
    body: Mapped[str] = mapped_column(Text, default="", server_default="")
    status: Mapped[MemoryItemStatus] = mapped_column(str_enum(MemoryItemStatus))
    priority: Mapped[MemoryItemPriority | None] = mapped_column(str_enum(MemoryItemPriority))
    why: Mapped[str | None] = mapped_column(Text)
    alternatives: Mapped[str | None] = mapped_column(Text)
    decided_at: Mapped[datetime | None]
    superseded_by_id: Mapped[uuid.UUID | None] = mapped_column(
        fk("memory_items", ondelete="SET NULL"), index=True
    )
    source: Mapped[MemoryItemSource] = mapped_column(
        str_enum(MemoryItemSource), default=MemoryItemSource.USER
    )
    source_message_id: Mapped[uuid.UUID | None] = mapped_column(
        fk("messages", ondelete="SET NULL"), index=True
    )
    source_agent_run_id: Mapped[uuid.UUID | None] = mapped_column(
        fk("agent_runs", ondelete="SET NULL"), index=True
    )
    stage_key: Mapped[str | None] = mapped_column(String(50))


class MemoryDependency(UserOwnedEntity):
    """Task `task_id` depends on task `depends_on_id` (same project, no cycles)."""

    __tablename__ = "memory_dependencies"
    __table_args__ = (
        UniqueConstraint("task_id", "depends_on_id"),
        CheckConstraint("task_id <> depends_on_id", name="not_self"),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(fk("projects", ondelete="CASCADE"), index=True)
    task_id: Mapped[uuid.UUID] = mapped_column(fk("memory_items", ondelete="CASCADE"), index=True)
    depends_on_id: Mapped[uuid.UUID] = mapped_column(
        fk("memory_items", ondelete="CASCADE"), index=True
    )
