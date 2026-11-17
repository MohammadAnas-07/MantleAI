"""Tables owned by the workflow module."""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import UserOwnedEntity, fk, str_enum


class WorkflowRunStatus(StrEnum):
    ACTIVE = "active"
    COMPLETED = "completed"
    ABANDONED = "abandoned"


class StageStatus(StrEnum):
    NOT_STARTED = "not_started"
    DRAFTING = "drafting"
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    CHANGES_REQUESTED = "changes_requested"
    SKIPPED = "skipped"


class AgentName(StrEnum):
    PLANNER = "planner"
    REVIEWER = "reviewer"


class AgentRunStatus(StrEnum):
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


class WorkflowRun(UserOwnedEntity):
    __tablename__ = "workflow_runs"

    project_id: Mapped[uuid.UUID] = mapped_column(fk("projects", ondelete="CASCADE"), index=True)
    status: Mapped[WorkflowRunStatus] = mapped_column(
        str_enum(WorkflowRunStatus), default=WorkflowRunStatus.ACTIVE
    )
    current_stage_key: Mapped[str | None] = mapped_column(String(50))


class StageState(UserOwnedEntity):
    """One row per stage per run. The stage list is fixed in code (D4)."""

    __tablename__ = "stage_states"
    __table_args__ = (UniqueConstraint("workflow_run_id", "stage_key"),)

    workflow_run_id: Mapped[uuid.UUID] = mapped_column(
        fk("workflow_runs", ondelete="CASCADE"), index=True
    )
    stage_key: Mapped[str] = mapped_column(String(50))
    position: Mapped[int]
    status: Mapped[StageStatus] = mapped_column(
        str_enum(StageStatus), default=StageStatus.NOT_STARTED
    )
    output: Mapped[str | None] = mapped_column(Text)
    decision_note: Mapped[str | None] = mapped_column(Text)
    decided_at: Mapped[datetime | None]


class AgentRun(UserOwnedEntity):
    __tablename__ = "agent_runs"

    stage_state_id: Mapped[uuid.UUID] = mapped_column(
        fk("stage_states", ondelete="CASCADE"), index=True
    )
    agent: Mapped[AgentName] = mapped_column(str_enum(AgentName))
    model_id: Mapped[uuid.UUID] = mapped_column(fk("model_configs"), index=True)
    input_summary: Mapped[str | None] = mapped_column(Text)
    output: Mapped[str | None] = mapped_column(Text)
    status: Mapped[AgentRunStatus] = mapped_column(
        str_enum(AgentRunStatus), default=AgentRunStatus.RUNNING
    )
    finished_at: Mapped[datetime | None]
