"""Request and response bodies of the workflow endpoints (rule 26)."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.modules.workflow.state import clean_reason


def _reason(value: str | None) -> str:
    return clean_reason(value)


# ---- workflow ------------------------------------------------------------------------------


class ChecklistItemOut(BaseModel):
    id: str
    text: str
    required: bool
    done: bool


class ArtifactOut(BaseModel):
    text: str
    kind: str
    statuses: list[str]
    have: int
    need: int
    met: bool


class UnmetOut(BaseModel):
    type: str  # checklist | artifact
    id: str
    text: str
    have: int | None = None
    need: int | None = None


class StageOut(BaseModel):
    id: str
    title: str
    goal: str
    status: str  # pending | current | approved | skipped
    checklist: list[ChecklistItemOut]
    artifacts: list[ArtifactOut]
    unmet: list[UnmetOut]
    ready: bool


class WorkflowEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    action: str
    stage_id: str | None
    item_id: str | None
    actor: str
    reason: str | None
    forced: bool
    details: dict[str, Any]
    created_at: datetime


class WorkflowOut(BaseModel):
    project_id: uuid.UUID
    status: str  # active | completed
    current_stage_id: str | None
    version: int
    stages: list[StageOut]
    events: list[WorkflowEventOut]


class StageDefinitionOut(BaseModel):
    id: str
    title: str
    goal: str
    checklist: list[dict[str, Any]]
    artifacts: list[dict[str, Any]]


class ChecklistIn(BaseModel):
    stage_id: str = Field(min_length=1, max_length=50)
    item_id: str = Field(min_length=1, max_length=50)
    done: bool = True


class ApproveIn(BaseModel):
    force: bool = False
    reason: str | None = None

    @model_validator(mode="after")
    def _force_needs_reason(self) -> "ApproveIn":
        if self.force or self.reason is not None:
            self.reason = clean_reason(self.reason)
        return self


class ReasonIn(BaseModel):
    reason: str

    @field_validator("reason")
    @classmethod
    def _check(cls, value: str) -> str:
        return _reason(value)


class ReopenIn(ReasonIn):
    stage_id: str = Field(min_length=1, max_length=50)


# ---- agent runs ----------------------------------------------------------------------------


class EmptyIn(BaseModel):
    """Write endpoints take a JSON body even when there is nothing to send (`{}`)."""

    model_config = ConfigDict(extra="forbid")


class GapFinderIn(BaseModel):
    model_id: uuid.UUID
    force: bool = False


class AgentRunIn(BaseModel):
    run_type: Literal["plan", "review"]
    model_id: uuid.UUID
    requirement_id: uuid.UUID | None = None
    requirement_text: str | None = None
    use_code_context: bool = False
    force: bool = False

    @model_validator(mode="after")
    def _requirement(self) -> "AgentRunIn":
        from app.core.config import settings

        if self.requirement_text is not None:
            self.requirement_text = self.requirement_text.strip() or None
        if self.run_type == "plan":
            if (self.requirement_id is None) == (self.requirement_text is None):
                raise ValueError(
                    "a plan run needs exactly one of requirement_id and requirement_text"
                )
            if (
                self.requirement_text
                and len(self.requirement_text) > settings.agent_requirement_max_chars
            ):
                raise ValueError(
                    "requirement_text must be at most "
                    f"{settings.agent_requirement_max_chars} characters"
                )
        elif self.requirement_id is not None or self.requirement_text is not None:
            raise ValueError("a review run takes no requirement")
        return self


class AgentRunStepOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    position: int
    agent: str
    prompt_version: str
    model_id: uuid.UUID
    status: str
    input_tokens_estimate: int
    attempts: int
    output: dict[str, Any]
    input_tokens: int
    output_tokens: int
    cost_usd: Decimal | None
    latency_ms: int
    error: str | None


class AgentRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    run_type: str
    status: str
    stage_id: str | None
    model_id: uuid.UUID
    prompt_version: str
    input: dict[str, Any]
    estimate: dict[str, Any]
    result: dict[str, Any]
    warnings: list[dict[str, Any]]
    error: str | None
    error_message: str | None
    error_details: dict[str, Any]
    input_tokens: int
    output_tokens: int
    cost_usd: Decimal | None
    cancel_requested_at: datetime | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    decided_at: datetime | None
    decision_reason: str | None
    saved_item_ids: list[str]
    steps: list[AgentRunStepOut] = []


class AgentRunPage(BaseModel):
    items: list[AgentRunOut]


class TaskEdit(BaseModel):
    index: int = Field(ge=0)
    title: str | None = None
    description: str | None = None
    priority: Literal["high", "medium", "low"] | None = None


class DecisionEdit(BaseModel):
    index: int = Field(ge=0)
    title: str | None = None
    what: str | None = None
    why: str | None = None
    alternatives: str | None = None


class ApproveRunIn(BaseModel):
    """`all` saves every proposed item; otherwise only the listed indexes, with any edits."""

    all: bool = False
    tasks: list[TaskEdit] = []
    decisions: list[DecisionEdit] = []

    @model_validator(mode="after")
    def _something(self) -> "ApproveRunIn":
        if not self.all and not self.tasks and not self.decisions:
            raise ValueError("choose all=true or list the tasks and decisions to save")
        return self


class ApproveRunOut(BaseModel):
    run: AgentRunOut
    task_ids: list[uuid.UUID]
    decision_ids: list[uuid.UUID]
    warnings: list[dict[str, Any]]
