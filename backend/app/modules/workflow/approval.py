"""The user's decision on a plan run: save all or some proposed items, or reject the run.

This is the only path from agent output to project memory. Edited text goes through the same
checks as manual input (in the projects module), and the save is one transaction: every chosen
item or none. Tasks are saved as todo and decisions as proposed, never accepted. A dependency on
a task the user didn't choose is left out, with a warning.
"""

import logging
import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.modules.projects.service import DraftDecision, DraftTask, add_agent_drafts
from app.modules.workflow.models import AgentRun, RunStatus, RunType
from app.modules.workflow.outputs import Plan, ProposedDecision, ProposedTask
from app.modules.workflow.run_setup import get_run, now
from app.modules.workflow.schemas import ApproveRunIn, DecisionEdit, TaskEdit

logger = logging.getLogger(__name__)


@dataclass
class Approval:
    run: AgentRun
    task_ids: list[uuid.UUID] = field(default_factory=list)
    decision_ids: list[uuid.UUID] = field(default_factory=list)
    warnings: list[dict[str, Any]] = field(default_factory=list)


def _waiting(run: AgentRun) -> None:
    if run.run_type != RunType.PLAN or run.status != RunStatus.WAITING_FOR_APPROVAL:
        raise AppError(
            f"Only a plan run waiting for approval can be decided (this one is {run.status}).",
            code="agent_run_not_waiting", status_code=409,
        )  # fmt: skip


def _pick[E: (TaskEdit, DecisionEdit)](edits: list[E], count: int, kind: str) -> list[E]:
    seen: set[int] = set()
    for edit in edits:
        if edit.index >= count:
            raise AppError(f"There is no proposed {kind} {edit.index}.", code="invalid_selection",
                           status_code=422)  # fmt: skip
        if edit.index in seen:
            raise AppError(f"Proposed {kind} {edit.index} is listed twice.",
                           code="invalid_selection", status_code=422)  # fmt: skip
        seen.add(edit.index)
    return sorted(edits, key=lambda e: e.index)


def _task_draft(task: ProposedTask, edit: TaskEdit, deps: tuple[int, ...]) -> DraftTask:
    """Edited fields are passed on exactly as typed: the projects module checks them like any
    hand-written item (one-line title, length, no control characters)."""
    title = edit.title if edit.title is not None else task.title
    description = edit.description if edit.description is not None else task.description
    body = task.model_copy(update={"description": description}).body()
    return DraftTask(title, body, edit.priority or task.priority, deps)


def _decision_draft(decision: ProposedDecision, edit: DecisionEdit) -> DraftDecision:
    def pick(edited: str | None, proposed: str) -> str:
        return edited if edited is not None else proposed

    return DraftDecision(
        pick(edit.title, decision.title), pick(edit.what, decision.what),
        pick(edit.why, decision.why), pick(edit.alternatives, decision.alternatives),
    )  # fmt: skip


async def approve_run(
    session: AsyncSession, user_id: uuid.UUID, run_id: uuid.UUID, body: ApproveRunIn
) -> Approval:
    run = await get_run(session, user_id, run_id)
    _waiting(run)
    plan = Plan.model_validate(run.result["plan"])
    if body.all:
        task_edits = [TaskEdit(index=i) for i in range(len(plan.tasks))]
        decision_edits = [DecisionEdit(index=i) for i in range(len(plan.decisions))]
    else:
        task_edits = _pick(body.tasks, len(plan.tasks), "task")
        decision_edits = _pick(body.decisions, len(plan.decisions), "decision")

    chosen = [e.index for e in task_edits]
    new_position = {plan_index: position for position, plan_index in enumerate(chosen)}
    result = Approval(run)
    drafts: list[DraftTask] = []
    for edit in task_edits:
        task = plan.tasks[edit.index]
        deps = []
        for dep in task.depends_on:
            if dep in new_position:
                deps.append(new_position[dep])
            else:
                result.warnings.append({"code": "dependency_not_saved", "task": edit.index,
                                        "depends_on": dep})  # fmt: skip
        drafts.append(_task_draft(task, edit, tuple(deps)))
    decisions = [_decision_draft(plan.decisions[e.index], e) for e in decision_edits]

    try:
        saved = await add_agent_drafts(
            session, user_id, run.project_id, agent_run_id=run.id, stage_key=run.stage_id,
            tasks=drafts, decisions=decisions,
        )  # fmt: skip
    except AppError as exc:
        if exc.code == "invalid_draft" and "index" in exc.details:
            # projects counts the chosen items; report the index in the plan instead.
            edits = task_edits if exc.details["kind"] == "task" else decision_edits
            exc.details["index"] = edits[exc.details["index"]].index
            first = exc.details["errors"][0]
            exc.message = (
                f"Proposed {exc.details['kind']} {exc.details['index']} is not valid: "
                f"{first['field']}: {first['message']}"
            )
        raise
    result.task_ids, result.decision_ids = saved.task_ids, saved.decision_ids
    run.status, run.decided_at = RunStatus.APPROVED, now()
    run.finished_at = run.finished_at or run.decided_at
    run.saved_item_ids = [str(i) for i in saved.task_ids + saved.decision_ids]
    await session.flush()
    logger.info("agent run approved run=%s tasks=%d decisions=%d", run.id,
                len(saved.task_ids), len(saved.decision_ids))  # fmt: skip
    return result


async def reject_run(
    session: AsyncSession, user_id: uuid.UUID, run_id: uuid.UUID, reason: str
) -> AgentRun:
    """Close the run without saving anything."""
    run = await get_run(session, user_id, run_id)
    _waiting(run)
    run.status, run.decided_at, run.decision_reason = RunStatus.REJECTED, now(), reason
    run.finished_at = run.finished_at or run.decided_at
    await session.flush()
    logger.info("agent run rejected run=%s", run.id)
    return run
