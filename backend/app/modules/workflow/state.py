"""Workflow state per project: the current stage, the checklist, gates and transitions.

Every change goes through `_save`, an UPDATE that only matches the version the caller read.
Two requests that read the same version can't both win: the second matches no row and gets
409 workflow_changed. Every action also writes one append-only WorkflowEvent.

No LLM call happens here; stage changes only come from the user's requests.
"""

import logging
import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import AppError
from app.modules.projects.service import MemoryRef, get_project, memory_refs
from app.modules.workflow.models import (
    ProjectWorkflow,
    StageStatus,
    WorkflowAction,
    WorkflowEvent,
    WorkflowStatus,
)
from app.modules.workflow.stages import MemoryCountRule, StageDefinition, StageList, get_stages

logger = logging.getLogger(__name__)

# Events in a workflow answer: the newest ones. The total is reported next to them.
EVENTS_SHOWN = 100


def conflict(code: str, message: str, **details: Any) -> AppError:
    """A 409 with a code, a message and details."""
    return AppError(message, code=code, status_code=409, details=details)


def clean_reason(value: str | None) -> str:
    """Trim a reason; it must be non-empty and at most WORKFLOW_REASON_MAX_LENGTH."""
    text = (value or "").strip()
    if not text:
        raise ValueError("a reason is required")
    if len(text) > settings.workflow_reason_max_length:
        raise ValueError(
            f"the reason must be at most {settings.workflow_reason_max_length} characters"
        )
    return text


# ---- reading -------------------------------------------------------------------------------


@dataclass(frozen=True)
class Unmet:
    type: str  # checklist | artifact
    id: str
    text: str
    have: int | None = None
    need: int | None = None

    def as_dict(self) -> dict[str, Any]:
        """The unmet item as it appears in a 409 and in an event."""
        out: dict[str, Any] = {"type": self.type, "id": self.id, "text": self.text}
        if self.have is not None:
            out["have"], out["need"] = self.have, self.need
        return out


@dataclass
class StageView:
    definition: StageDefinition
    status: StageStatus
    ticked: set[str]
    artifacts: list[tuple[MemoryCountRule, int]]

    @property
    def unmet(self) -> list[Unmet]:
        """Required checklist items not ticked and artifact rules not met."""
        out = [
            Unmet("checklist", i.id, i.text)
            for i in self.definition.checklist
            if i.required and i.id not in self.ticked
        ]
        for position, (rule, have) in enumerate(self.artifacts):
            if have < rule.min:
                out.append(Unmet("artifact", f"artifact_{position}", rule.text, have, rule.min))
        return out


@dataclass
class WorkflowView:
    workflow: ProjectWorkflow
    stages: list[StageView]
    events: list[WorkflowEvent] = field(default_factory=list)  # the newest EVENTS_SHOWN
    events_total: int = 0
    # The memory the gates were counted from; a transition reuses it (it doesn't change it).
    memory: list[MemoryRef] = field(default_factory=list)

    @property
    def current(self) -> StageView | None:
        """The current stage, or None when the workflow is completed."""
        return next((s for s in self.stages if s.status == StageStatus.CURRENT), None)


def _count(rule: MemoryCountRule, memory: list[MemoryRef]) -> int:
    return sum(
        1
        for m in memory
        if m.kind == rule.kind and (not rule.statuses or m.status in rule.statuses)
    )


def _status(workflow: ProjectWorkflow, stage: StageDefinition) -> StageStatus:
    if workflow.current_stage_id == stage.id:
        return StageStatus.CURRENT
    stored = workflow.stage_statuses.get(stage.id)
    if stored in (StageStatus.APPROVED, StageStatus.SKIPPED):
        return StageStatus(stored)
    return StageStatus.PENDING


def _check_known(workflow: ProjectWorkflow, stages: StageList) -> None:
    if workflow.current_stage_id is not None and stages.get(workflow.current_stage_id) is None:
        raise conflict(
            "unknown_stage",
            f"The workflow is at stage {workflow.current_stage_id!r}, which no longer exists in "
            "the stage definitions. Reset the workflow with "
            f"POST /api/v1/projects/{workflow.project_id}/workflow/reset.",
            stage_id=workflow.current_stage_id,
            reset_path=f"/api/v1/projects/{workflow.project_id}/workflow/reset",
        )


async def get_or_create(
    session: AsyncSession, user_id: uuid.UUID, project_id: uuid.UUID
) -> ProjectWorkflow:
    """The project's stored workflow. A project without one (made before this feature, or
    new) gets one at the first stage, with a "created" event, on its first change."""
    await get_project(session, user_id, project_id)  # 404 for another user's project
    found = await _load(session, user_id, project_id)
    if found is not None:
        return found
    workflow = _default(user_id, project_id)
    try:
        async with session.begin_nested():
            session.add(workflow)
            await session.flush()
            session.add(_event(workflow, WorkflowAction.CREATED, workflow.current_stage_id))
            await session.flush()
    except IntegrityError:
        # Another request created it first; use theirs.
        found = await _load(session, user_id, project_id)
        assert found is not None
        return found
    logger.info("workflow created project=%s", project_id)
    return workflow


async def _load(
    session: AsyncSession, user_id: uuid.UUID, project_id: uuid.UUID
) -> ProjectWorkflow | None:
    return await session.scalar(
        select(ProjectWorkflow).where(
            ProjectWorkflow.user_id == user_id, ProjectWorkflow.project_id == project_id
        )
    )


def _default(user_id: uuid.UUID, project_id: uuid.UUID) -> ProjectWorkflow:
    """The state a project without a stored workflow has: first stage, nothing ticked. Not
    added to the session, so reading it writes nothing (rule 28)."""
    return ProjectWorkflow(
        user_id=user_id, project_id=project_id, status=WorkflowStatus.ACTIVE,
        current_stage_id=get_stages().first.id, stage_statuses={}, checklist={}, version=1,
    )  # fmt: skip


async def view(
    session: AsyncSession,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
    *,
    events: bool = True,
    create: bool = True,
) -> WorkflowView:
    """The state with gate status per stage. 409 unknown_stage if the stored stage is gone.

    With `create=False` (GET requests) a project without a stored workflow gets the default
    state and nothing is written; the first change stores it.
    """
    if create:
        workflow = await get_or_create(session, user_id, project_id)
    else:
        await get_project(session, user_id, project_id)
        workflow = await _load(session, user_id, project_id) or _default(user_id, project_id)
    _check_known(workflow, get_stages())
    memory = await memory_refs(session, user_id, project_id)
    result = WorkflowView(workflow, _stage_views(workflow, memory), memory=memory)
    if events:
        await _load_events(session, user_id, result)
    return result


def _stage_views(workflow: ProjectWorkflow, memory: list[MemoryRef]) -> list[StageView]:
    return [
        StageView(
            definition=stage,
            status=_status(workflow, stage),
            ticked=set(workflow.checklist.get(stage.id, [])),
            artifacts=[(rule, _count(rule, memory)) for rule in stage.artifacts],
        )
        for stage in get_stages().stages
    ]


async def _load_events(session: AsyncSession, user_id: uuid.UUID, result: WorkflowView) -> None:
    """The newest EVENTS_SHOWN events, oldest first, and the total (counted only when the
    history is longer than that)."""
    workflow = result.workflow
    if workflow.id is None:
        return
    mine = (WorkflowEvent.user_id == user_id, WorkflowEvent.workflow_id == workflow.id)
    rows = list(await session.scalars(
        select(WorkflowEvent).where(*mine).order_by(WorkflowEvent.seq.desc()).limit(EVENTS_SHOWN)
    ))  # fmt: skip
    result.events = rows[::-1]
    result.events_total = len(rows)
    if len(rows) == EVENTS_SHOWN:
        result.events_total = int(
            await session.scalar(select(func.count()).select_from(WorkflowEvent).where(*mine)) or 0
        )


async def _after_change(
    session: AsyncSession, user_id: uuid.UUID, before: WorkflowView
) -> WorkflowView:
    """The state after a transition. `_save` refreshed the workflow; memory is what was read
    before the change, since a transition never changes it."""
    result = WorkflowView(before.workflow, _stage_views(before.workflow, before.memory),
                          memory=before.memory)  # fmt: skip
    await _load_events(session, user_id, result)
    return result


async def current_stage(
    session: AsyncSession, user_id: uuid.UUID, project_id: uuid.UUID
) -> StageView:
    """The stage agents work on: the current one, or the last one once completed."""
    state = await view(session, user_id, project_id, events=False)
    return state.current or state.stages[-1]


# ---- writing -------------------------------------------------------------------------------


def _event(
    workflow: ProjectWorkflow,
    action: WorkflowAction,
    stage_id: str | None,
    *,
    item_id: str | None = None,
    reason: str | None = None,
    forced: bool = False,
    details: dict[str, Any] | None = None,
) -> WorkflowEvent:
    return WorkflowEvent(
        user_id=workflow.user_id,
        project_id=workflow.project_id,
        workflow_id=workflow.id,
        action=action,
        stage_id=stage_id,
        item_id=item_id,
        reason=reason,
        forced=forced,
        details=details or {},
    )


async def _save(
    session: AsyncSession,
    workflow: ProjectWorkflow,
    events: list[WorkflowEvent],
    **values: Any,
) -> None:
    """Write `values` if nobody changed the workflow since it was read; else 409."""
    result = await session.execute(
        update(ProjectWorkflow)
        .where(
            ProjectWorkflow.id == workflow.id,
            ProjectWorkflow.user_id == workflow.user_id,
            ProjectWorkflow.version == workflow.version,
        )
        .values(version=workflow.version + 1, **values)
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        raise conflict(
            "workflow_changed",
            "The workflow was changed by another request. Load it again and retry.",
        )
    session.add_all(events)
    await session.flush()
    await session.refresh(workflow)


def _stage_or_404(stages: StageList, stage_id: str) -> StageDefinition:
    stage = stages.get(stage_id)
    if stage is None:
        raise AppError(
            f"There is no stage {stage_id!r}.", code="unknown_stage_id", status_code=422,
            details={"stage_id": stage_id},
        )  # fmt: skip
    return stage


async def set_item(
    session: AsyncSession,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
    stage_id: str,
    item_id: str,
    done: bool,
) -> WorkflowView:
    """Tick or untick one checklist item of any stage."""
    state = await view(session, user_id, project_id, events=False)
    stage = _stage_or_404(get_stages(), stage_id)
    if stage.item(item_id) is None:
        raise AppError(
            f"Stage {stage_id!r} has no checklist item {item_id!r}.",
            code="unknown_checklist_item", status_code=422,
            details={"stage_id": stage_id, "item_id": item_id},
        )  # fmt: skip
    workflow = state.workflow
    ticked = set(workflow.checklist.get(stage_id, []))
    ticked = ticked | {item_id} if done else ticked - {item_id}
    checklist = {**workflow.checklist, stage_id: sorted(ticked)}
    action = WorkflowAction.TICK if done else WorkflowAction.UNTICK
    await _save(session, workflow, [_event(workflow, action, stage_id, item_id=item_id)],
                checklist=checklist)  # fmt: skip
    return await _after_change(session, user_id, state)


async def _advance(
    session: AsyncSession,
    state: WorkflowView,
    to: StageStatus,
    events: list[WorkflowEvent],
) -> None:
    workflow = state.workflow
    current = state.current
    assert current is not None  # approve and skip check this first
    stages = get_stages()
    following = stages.after(current.definition.id)
    statuses = {**workflow.stage_statuses, current.definition.id: to.value}
    values: dict[str, Any] = {"stage_statuses": statuses}
    if following is None:
        values |= {"current_stage_id": None, "status": WorkflowStatus.COMPLETED}
        events.append(_event(workflow, WorkflowAction.COMPLETED, None))
    else:
        values["current_stage_id"] = following.id
    await _save(session, workflow, events, **values)


def _current_or_409(state: WorkflowView, expected_stage_id: str | None) -> StageView:
    """The current stage. 409 when the workflow is completed, or when the caller names the
    stage it means and that is no longer the current one (another request moved it)."""
    current = state.current
    if current is None:
        raise conflict("workflow_completed", "The workflow is completed. Reopen a stage first.")
    if expected_stage_id is not None and expected_stage_id != current.definition.id:
        raise conflict(
            "workflow_changed",
            f"The current stage is now {current.definition.id!r}, not {expected_stage_id!r}. "
            "Load the workflow again.",
            stage_id=current.definition.id,
        )
    return current


async def approve(
    session: AsyncSession,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
    *,
    force: bool = False,
    reason: str | None = None,
    stage_id: str | None = None,
) -> WorkflowView:
    """Approve the current stage and move to the next one. 409 with the unmet list when the
    gate isn't met, unless `force` (which needs a reason, checked by the schema). `stage_id`
    is the stage the user means to approve; see `_current_or_409`."""
    state = await view(session, user_id, project_id, events=False)
    current = _current_or_409(state, stage_id)
    unmet = [u.as_dict() for u in current.unmet]
    if unmet and not force:
        raise conflict(
            "stage_gate_unmet",
            f"Stage {current.definition.id!r} can't be approved yet.",
            stage_id=current.definition.id,
            unmet=unmet,
        )
    if force and not reason:
        raise AppError("A forced approval needs a reason.", code="reason_required",
                       status_code=422)  # fmt: skip
    workflow = state.workflow
    event = _event(
        workflow, WorkflowAction.APPROVE, current.definition.id, reason=reason,
        forced=bool(force and unmet), details={"unmet": unmet} if unmet else {},
    )  # fmt: skip
    await _advance(session, state, StageStatus.APPROVED, [event])
    logger.info("stage approved project=%s stage=%s forced=%s", project_id,
                current.definition.id, bool(force and unmet))  # fmt: skip
    return await _after_change(session, user_id, state)


async def skip(
    session: AsyncSession, user_id: uuid.UUID, project_id: uuid.UUID, *, reason: str,
    stage_id: str | None = None,
) -> WorkflowView:  # fmt: skip
    """Skip the current stage (no gate), with a reason."""
    state = await view(session, user_id, project_id, events=False)
    current = _current_or_409(state, stage_id)
    event = _event(state.workflow, WorkflowAction.SKIP, current.definition.id, reason=reason)
    await _advance(session, state, StageStatus.SKIPPED, [event])
    return await _after_change(session, user_id, state)


async def reopen(
    session: AsyncSession, user_id: uuid.UUID, project_id: uuid.UUID, *, stage_id: str,
    reason: str,
) -> WorkflowView:  # fmt: skip
    """Go back to an earlier stage. It and every later stage become pending again; ticks stay."""
    state = await view(session, user_id, project_id, events=False)
    stages = get_stages()
    target = _stage_or_404(stages, stage_id)
    current = state.current
    if current is not None and stages.index(target.id) >= stages.index(current.definition.id):
        raise conflict(
            "not_an_earlier_stage",
            f"Only a stage before the current one ({current.definition.id!r}) can be reopened.",
            stage_id=stage_id,
        )
    workflow = state.workflow
    later = {s.id for s in stages.stages[stages.index(target.id) :]}
    statuses = {k: v for k, v in workflow.stage_statuses.items() if k not in later}
    event = _event(workflow, WorkflowAction.REOPEN, target.id, reason=reason,
                   details={"from_stage_id": workflow.current_stage_id})  # fmt: skip
    await _save(session, workflow, [event], current_stage_id=target.id,
                status=WorkflowStatus.ACTIVE, stage_statuses=statuses)  # fmt: skip
    return await _after_change(session, user_id, state)


async def reset(
    session: AsyncSession, user_id: uuid.UUID, project_id: uuid.UUID, *, reason: str
) -> WorkflowView:
    """Back to the first stage; statuses cleared. Ticks of stages that still exist stay. Works
    even when the stored stage no longer exists (that is what it is for)."""
    workflow = await get_or_create(session, user_id, project_id)
    stages = get_stages()
    known = {s.id for s in stages.stages}
    checklist = {k: v for k, v in workflow.checklist.items() if k in known}
    event = _event(workflow, WorkflowAction.RESET, stages.first.id, reason=reason,
                   details={"from_stage_id": workflow.current_stage_id})  # fmt: skip
    await _save(session, workflow, [event], current_stage_id=stages.first.id,
                status=WorkflowStatus.ACTIVE, stage_statuses={}, checklist=checklist)  # fmt: skip
    return await view(session, user_id, project_id)
