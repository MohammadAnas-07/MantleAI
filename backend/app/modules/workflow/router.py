"""Workflow endpoints (docs/api-outline.md, "Workflow and agents"). Routes stay thin; the rules
live in state.py and the agent files."""

import uuid
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUserId, DbSession, SessionFactoryDep
from app.modules.llm.service import Gateway, get_gateway
from app.modules.workflow import approval, gap_finder, runs, state
from app.modules.workflow.models import AgentRun, AgentRunStep, RunType
from app.modules.workflow.run_setup import get_run
from app.modules.workflow.schemas import (
    AgentRunIn,
    AgentRunOut,
    AgentRunPage,
    AgentRunStepOut,
    ApproveIn,
    ApproveRunIn,
    ApproveRunOut,
    ArtifactOut,
    ChecklistIn,
    ChecklistItemOut,
    EmptyIn,
    GapFinderIn,
    ReasonIn,
    ReopenIn,
    StageDefinitionOut,
    StageOut,
    UnmetOut,
    WorkflowEventOut,
    WorkflowOut,
)
from app.modules.workflow.stages import get_stages

router = APIRouter(tags=["workflow"])

GatewayDep = Annotated[Gateway, Depends(get_gateway)]


async def run_out(session: AsyncSession, run: AgentRun) -> AgentRunOut:
    steps = await session.scalars(
        select(AgentRunStep)
        .where(AgentRunStep.user_id == run.user_id, AgentRunStep.run_id == run.id)
        .order_by(AgentRunStep.position)
    )
    out = AgentRunOut.model_validate(run)
    out.steps = [AgentRunStepOut.model_validate(s) for s in steps]
    return out


def workflow_out(view: state.WorkflowView) -> WorkflowOut:
    stages = []
    for stage in view.stages:
        unmet = stage.unmet
        stages.append(
            StageOut(
                id=stage.definition.id,
                title=stage.definition.title,
                goal=stage.definition.goal,
                status=stage.status.value,
                checklist=[
                    ChecklistItemOut(
                        id=i.id, text=i.text, required=i.required, done=i.id in stage.ticked
                    )  # fmt: skip
                    for i in stage.definition.checklist
                ],
                artifacts=[
                    ArtifactOut(
                        text=rule.text,
                        kind=rule.kind,
                        statuses=list(rule.statuses),
                        have=have,
                        need=rule.min,
                        met=have >= rule.min,
                    )  # fmt: skip
                    for rule, have in stage.artifacts
                ],
                unmet=[UnmetOut(**u.as_dict()) for u in unmet],
                ready=not unmet,
            )
        )
    workflow = view.workflow
    return WorkflowOut(
        project_id=workflow.project_id,
        status=str(workflow.status),
        current_stage_id=workflow.current_stage_id,
        version=workflow.version,
        stages=stages,
        events=[WorkflowEventOut.model_validate(e) for e in view.events],
    )


@router.get("/workflow/stages")
async def list_stages() -> list[StageDefinitionOut]:
    """The stage definitions, in order."""
    return [
        StageDefinitionOut(
            id=s.id,
            title=s.title,
            goal=s.goal,
            checklist=[i.model_dump() for i in s.checklist],
            artifacts=[r.model_dump() for r in s.artifacts],
        )
        for s in get_stages().stages
    ]


@router.get("/projects/{project_id}/workflow")
async def get_workflow(
    project_id: uuid.UUID, session: DbSession, user_id: CurrentUserId
) -> WorkflowOut:
    """Stage, checklist, gate status and events. Created at the first stage on first access."""
    view = await state.view(session, user_id, project_id)
    await session.commit()
    return workflow_out(view)


@router.post("/projects/{project_id}/workflow/checklist")
async def set_checklist_item(
    project_id: uuid.UUID, body: ChecklistIn, session: DbSession, user_id: CurrentUserId
) -> WorkflowOut:
    view = await state.set_item(
        session, user_id, project_id, body.stage_id, body.item_id, body.done
    )
    await session.commit()
    return workflow_out(view)


@router.post("/projects/{project_id}/workflow/approve")
async def approve_stage(
    project_id: uuid.UUID, body: ApproveIn, session: DbSession, user_id: CurrentUserId
) -> WorkflowOut:
    """Approve the current stage. 409 stage_gate_unmet lists what is missing, unless
    force=true with a reason."""
    view = await state.approve(session, user_id, project_id, force=body.force, reason=body.reason)
    await session.commit()
    return workflow_out(view)


@router.post("/projects/{project_id}/workflow/skip")
async def skip_stage(
    project_id: uuid.UUID, body: ReasonIn, session: DbSession, user_id: CurrentUserId
) -> WorkflowOut:
    view = await state.skip(session, user_id, project_id, reason=body.reason)
    await session.commit()
    return workflow_out(view)


@router.post("/projects/{project_id}/workflow/reopen")
async def reopen_stage(
    project_id: uuid.UUID, body: ReopenIn, session: DbSession, user_id: CurrentUserId
) -> WorkflowOut:
    view = await state.reopen(
        session, user_id, project_id, stage_id=body.stage_id, reason=body.reason
    )
    await session.commit()
    return workflow_out(view)


@router.post("/projects/{project_id}/workflow/reset")
async def reset_workflow(
    project_id: uuid.UUID, body: ReasonIn, session: DbSession, user_id: CurrentUserId
) -> WorkflowOut:
    """Back to the first stage. Also the way out when the stored stage no longer exists."""
    view = await state.reset(session, user_id, project_id, reason=body.reason)
    await session.commit()
    return workflow_out(view)


@router.post("/projects/{project_id}/gap-finder")
async def run_gap_finder(
    project_id: uuid.UUID,
    body: GapFinderIn,
    session: DbSession,
    user_id: CurrentUserId,
    gateway: GatewayDep,
) -> AgentRunOut:
    """Find gaps for the current stage now (one model call, purpose agent_run). A failed run
    is saved, then its error is returned."""
    run, error = await gap_finder.run_gap_finder(
        session, gateway, user_id, project_id, body.model_id, force=body.force
    )
    out = await run_out(session, run)
    await session.commit()
    if error is not None:
        raise error
    return out


@router.get("/projects/{project_id}/gap-finder")
async def list_gap_finder_runs(
    project_id: uuid.UUID, session: DbSession, user_id: CurrentUserId
) -> AgentRunPage:
    """Past gap finder results, newest first."""
    runs = await gap_finder.list_gap_runs(session, user_id, project_id)
    return AgentRunPage(items=[await run_out(session, r) for r in runs])


@router.post("/projects/{project_id}/agent-runs", status_code=202)
async def start_agent_run(
    project_id: uuid.UUID,
    body: AgentRunIn,
    background: BackgroundTasks,
    session: DbSession,
    user_id: CurrentUserId,
    gateway: GatewayDep,
    session_factory: SessionFactoryDep,
) -> AgentRunOut:
    """Start a plan (Planner, then Reviewer) or review (Reviewer only) run in the background.
    The response carries the estimate; poll GET /agent-runs/{id}. 409 when a run is active or
    the estimate is over the cost limit without force; 413 when the prompt doesn't fit."""
    run = await runs.start_run(
        session, gateway, user_id, project_id, run_type=RunType(body.run_type),
        model_id=body.model_id, requirement_id=body.requirement_id,
        requirement_text=body.requirement_text, use_code_context=body.use_code_context,
        force=body.force,
    )  # fmt: skip
    out = await run_out(session, run)
    await session.commit()
    background.add_task(runs.run_agent_job, session_factory, gateway, user_id, run.id)
    return out


@router.get("/projects/{project_id}/agent-runs")
async def list_agent_runs(
    project_id: uuid.UUID, session: DbSession, user_id: CurrentUserId
) -> AgentRunPage:
    """Plan and review runs, newest first."""
    found = await runs.list_runs(session, user_id, project_id)
    return AgentRunPage(items=[await run_out(session, r) for r in found])


@router.get("/agent-runs/{run_id}")
async def get_agent_run(
    run_id: uuid.UUID, session: DbSession, user_id: CurrentUserId
) -> AgentRunOut:
    return await run_out(session, await get_run(session, user_id, run_id))


@router.post("/agent-runs/{run_id}/cancel")
async def cancel_agent_run(
    run_id: uuid.UUID, body: EmptyIn, session: DbSession, user_id: CurrentUserId
) -> AgentRunOut:
    """Queued: cancelled now. Running: stops before its next step."""
    run = await runs.request_cancel(session, user_id, run_id)
    out = await run_out(session, run)
    await session.commit()
    return out


@router.post("/agent-runs/{run_id}/approve")
async def approve_agent_run(
    run_id: uuid.UUID, body: ApproveRunIn, session: DbSession, user_id: CurrentUserId
) -> ApproveRunOut:
    """Save all or the chosen proposed items (with edits) to project memory, in one
    transaction. Tasks become todo, decisions proposed."""
    result = await approval.approve_run(session, user_id, run_id, body)
    out = await run_out(session, result.run)
    await session.commit()
    return ApproveRunOut(run=out, task_ids=result.task_ids, decision_ids=result.decision_ids,
                         warnings=result.warnings)  # fmt: skip


@router.post("/agent-runs/{run_id}/reject")
async def reject_agent_run(
    run_id: uuid.UUID, body: ReasonIn, session: DbSession, user_id: CurrentUserId
) -> AgentRunOut:
    """Close the run with a reason. Nothing is saved."""
    run = await approval.reject_run(session, user_id, run_id, body.reason)
    out = await run_out(session, run)
    await session.commit()
    return out
