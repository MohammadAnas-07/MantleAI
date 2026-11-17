"""Tables owned by the projects module: Project and MemoryItem."""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import UserOwnedEntity, fk, str_enum


class MemoryItemKind(StrEnum):
    REQUIREMENT = "requirement"
    DECISION = "decision"
    TASK = "task"


class MemoryItemStatus(StrEnum):
    PROPOSED = "proposed"
    ACTIVE = "active"
    DONE = "done"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"


class MemoryItemPriority(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


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
    """Requirements, decisions and tasks in one table."""

    __tablename__ = "memory_items"

    project_id: Mapped[uuid.UUID] = mapped_column(fk("projects", ondelete="CASCADE"), index=True)
    kind: Mapped[MemoryItemKind] = mapped_column(str_enum(MemoryItemKind))
    title: Mapped[str] = mapped_column(String(300))
    body: Mapped[str] = mapped_column(Text, default="", server_default="")
    status: Mapped[MemoryItemStatus] = mapped_column(
        str_enum(MemoryItemStatus), default=MemoryItemStatus.ACTIVE
    )
    priority: Mapped[MemoryItemPriority | None] = mapped_column(str_enum(MemoryItemPriority))
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
