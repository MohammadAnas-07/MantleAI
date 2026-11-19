"""Workflow endpoints (docs/api-outline.md, "Workflow and agents"). Routes stay thin; the rules
live in state.py and the agent files."""

import uuid

from fastapi import APIRouter

from app.api.deps import CurrentUserId, DbSession
from app.modules.workflow import state
from app.modules.workflow.schemas import (
    ApproveIn,
    ArtifactOut,
    ChecklistIn,
    ChecklistItemOut,
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
