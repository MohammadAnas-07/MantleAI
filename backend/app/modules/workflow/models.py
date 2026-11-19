"""Tables owned by the workflow module (migration 0008).

- ProjectWorkflow: one row per project: the current stage, what is ticked, and a version
  number that makes two simultaneous transitions fail cleanly instead of both winning.
- WorkflowEvent: every action on the workflow, append-only.
- AgentRun: one Planner/Reviewer run or one gap finder run, with its result and decision.
- AgentRunStep: one model call inside a run (planner, reviewer or gap_finder).
"""

import uuid
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from sqlalchemy import BigInteger, Identity, Index, Numeric, String, Text, event, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import UserOwnedEntity, fk, str_enum


class WorkflowStatus(StrEnum):
    ACTIVE = "active"
    COMPLETED = "completed"


class StageStatus(StrEnum):
    PENDING = "pending"
    CURRENT = "current"
    APPROVED = "approved"
    SKIPPED = "skipped"


class WorkflowAction(StrEnum):
    CREATED = "created"
    TICK = "tick"
    UNTICK = "untick"
    APPROVE = "approve"
    SKIP = "skip"
    REOPEN = "reopen"
    RESET = "reset"
    COMPLETED = "completed"


class RunType(StrEnum):
    PLAN = "plan"  # Planner, then Reviewer
    REVIEW = "review"  # Reviewer only, on the current memory
    GAP_FINDER = "gap_finder"


class RunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    WAITING_FOR_APPROVAL = "waiting_for_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    COMPLETED = "completed"  # a gap finder or review run: nothing to approve
    FAILED = "failed"
    CANCELLED = "cancelled"


ACTIVE_RUN_STATUSES = (RunStatus.QUEUED, RunStatus.RUNNING)


class AgentName(StrEnum):
    PLANNER = "planner"
    REVIEWER = "reviewer"
    GAP_FINDER = "gap_finder"


class ProjectWorkflow(UserOwnedEntity):
    __tablename__ = "project_workflows"

    project_id: Mapped[uuid.UUID] = mapped_column(
        fk("projects", ondelete="CASCADE"), index=True, unique=True
    )
    status: Mapped[WorkflowStatus] = mapped_column(
        str_enum(WorkflowStatus), default=WorkflowStatus.ACTIVE
    )
    # Null once the workflow is completed. May name a stage that was later removed from the
    # YAML; the service reports that as 409 unknown_stage, never a crash.
    current_stage_id: Mapped[str | None] = mapped_column(String(50))
    # stage id -> approved | skipped. Stages not listed are pending (or current).
    stage_statuses: Mapped[dict[str, Any]] = mapped_column(default=dict, server_default="{}")
    # stage id -> list of ticked checklist item ids.
    checklist: Mapped[dict[str, Any]] = mapped_column(default=dict, server_default="{}")
    # Bumped by every transition; an update that sees another version loses with 409.
    version: Mapped[int] = mapped_column(default=1, server_default="1")


class WorkflowEvent(UserOwnedEntity):
    """Append-only. The ORM refuses updates and a database trigger refuses them too; rows go
    away only with their project."""

    __tablename__ = "workflow_events"

    # Insertion order. Events of one transaction share created_at, so this is the sort key.
    seq: Mapped[int] = mapped_column(BigInteger, Identity(), index=True)
    project_id: Mapped[uuid.UUID] = mapped_column(fk("projects", ondelete="CASCADE"), index=True)
    workflow_id: Mapped[uuid.UUID] = mapped_column(
        fk("project_workflows", ondelete="CASCADE"), index=True
    )
    action: Mapped[WorkflowAction] = mapped_column(str_enum(WorkflowAction))
    stage_id: Mapped[str | None] = mapped_column(String(50))
    item_id: Mapped[str | None] = mapped_column(String(50))
    actor: Mapped[str] = mapped_column(String(32), default="user", server_default="user")
    reason: Mapped[str | None] = mapped_column(Text)
    forced: Mapped[bool] = mapped_column(default=False, server_default="false")
    # Facts about the action, such as the unmet gate items a forced approval skipped.
    details: Mapped[dict[str, Any]] = mapped_column(default=dict, server_default="{}")


@event.listens_for(WorkflowEvent, "before_update")
def _refuse_event_update(*_: Any) -> None:
    raise RuntimeError("workflow events are append-only")


class AgentRun(UserOwnedEntity):
    __tablename__ = "agent_runs"
    __table_args__ = (
        # One queued or running run per project.
        Index(
            "uq_agent_runs_project_id_active",
            "project_id",
            unique=True,
            postgresql_where=text("status IN ('queued', 'running')"),
        ),
    )

    project_id: Mapped[uuid.UUID] = mapped_column(fk("projects", ondelete="CASCADE"), index=True)
    run_type: Mapped[RunType] = mapped_column(str_enum(RunType))
    status: Mapped[RunStatus] = mapped_column(str_enum(RunStatus), default=RunStatus.QUEUED)
    stage_id: Mapped[str | None] = mapped_column(String(50))
    model_id: Mapped[uuid.UUID] = mapped_column(fk("model_configs"), index=True)
    # Comma-separated prompt files used, e.g. "planner_v1,reviewer_v1".
    prompt_version: Mapped[str] = mapped_column(String(100))
    # What the user asked for: requirement id or text, use_code_context, force.
    input: Mapped[dict[str, Any]] = mapped_column(default=dict, server_default="{}")
    estimate: Mapped[dict[str, Any]] = mapped_column(default=dict, server_default="{}")
    # The validated plan, review or gap report (drafts only; nothing here is memory yet).
    result: Mapped[dict[str, Any]] = mapped_column(default=dict, server_default="{}")
    warnings: Mapped[list[dict[str, Any]]] = mapped_column(default=list, server_default="[]")
    error: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(Text)
    error_details: Mapped[dict[str, Any]] = mapped_column(default=dict, server_default="{}")
    input_tokens: Mapped[int] = mapped_column(default=0, server_default="0")
    output_tokens: Mapped[int] = mapped_column(default=0, server_default="0")
    cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))
    cancel_requested_at: Mapped[datetime | None]
    started_at: Mapped[datetime | None]
    finished_at: Mapped[datetime | None]
    decided_at: Mapped[datetime | None]
    decision_reason: Mapped[str | None] = mapped_column(Text)
    # Memory items created when the user approved the run.
    saved_item_ids: Mapped[list[str]] = mapped_column(default=list, server_default="[]")


class AgentRunStep(UserOwnedEntity):
    __tablename__ = "agent_run_steps"

    run_id: Mapped[uuid.UUID] = mapped_column(fk("agent_runs", ondelete="CASCADE"), index=True)
    position: Mapped[int]
    agent: Mapped[AgentName] = mapped_column(str_enum(AgentName))
    prompt_version: Mapped[str] = mapped_column(String(50))
    model_id: Mapped[uuid.UUID] = mapped_column(fk("model_configs"), index=True)
    status: Mapped[str] = mapped_column(String(32))  # succeeded | failed
    input_tokens_estimate: Mapped[int] = mapped_column(default=0, server_default="0")
    attempts: Mapped[int] = mapped_column(default=0, server_default="0")
    output: Mapped[dict[str, Any]] = mapped_column(default=dict, server_default="{}")
    input_tokens: Mapped[int] = mapped_column(default=0, server_default="0")
    output_tokens: Mapped[int] = mapped_column(default=0, server_default="0")
    cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))
    latency_ms: Mapped[int] = mapped_column(default=0, server_default="0")
    error: Mapped[str | None] = mapped_column(String(64))
