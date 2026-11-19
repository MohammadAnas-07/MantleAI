"""The gap finder: one user-requested model call that lists missing steps, risks, technical
debt and scalability concerns for the current stage. Not an agent: it proposes nothing to
save. Each call is stored as an agent run of type gap_finder, so past results stay visible.

It runs inside the request (one call, at most one retry), and holds the project's single
active-run slot while it does.
"""

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError
from app.modules.llm.service import Gateway
from app.modules.projects.service import get_project, memory_refs
from app.modules.workflow.context import (
    AgentInputs,
    check_fits,
    load_memory,
    messages,
    project_text,
    stage_text,
)
from app.modules.workflow.models import AgentName, AgentRun, RunStatus, RunType
from app.modules.workflow.outputs import GapReport, References, check_references
from app.modules.workflow.prompts import GAP_FINDER_PROMPT
from app.modules.workflow.run_setup import (
    chat_model_with_key,
    check_cost,
    create_run,
    estimate,
    fail,
    now,
)
from app.modules.workflow.state import current_stage
from app.modules.workflow.steps import run_step

logger = logging.getLogger(__name__)


def trimmed_warning(dropped: int) -> list[dict[str, object]]:
    if not dropped:
        return []
    return [{"code": "memory_trimmed", "count": dropped,
             "message": f"{dropped} memory items did not fit and were left out."}]  # fmt: skip


async def run_gap_finder(
    session: AsyncSession,
    gateway: Gateway,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
    model_id: uuid.UUID,
    *,
    force: bool = False,
) -> tuple[AgentRun, AppError | None]:
    """Run it now. Checks (project, model, key, size, cost, active run) raise before any call.
    Returns the stored run and, when it failed, the error to report after the caller commits
    the failed run."""
    project = await get_project(session, user_id, project_id)
    model = await chat_model_with_key(session, user_id, model_id)
    stage = await current_stage(session, user_id, project_id)
    memory = await memory_refs(session, user_id, project_id)
    inputs = AgentInputs(project=project, stage=stage, memory=memory)
    await load_memory(session, gateway, user_id, project_id, model, inputs)
    prompt = messages(
        GAP_FINDER_PROMPT,
        [project_text(project, memory), stage_text(stage), inputs.memory_text],
    )
    tokens = await check_fits(session, gateway, user_id, model, prompt)
    run_estimate = estimate(model, [tokens])
    check_cost(run_estimate, force)
    run = await create_run(
        session, user_id=user_id, project_id=project_id, run_type=RunType.GAP_FINDER,
        status=RunStatus.RUNNING, model=model, stage_id=stage.definition.id,
        prompt_version=GAP_FINDER_PROMPT, run_input={"force": force}, run_estimate=run_estimate,
    )  # fmt: skip
    error: AppError | None = None
    try:
        report = await run_step(
            session, gateway, run, agent=AgentName.GAP_FINDER, prompt_version=GAP_FINDER_PROMPT,
            position=0, model=model, prompt=prompt, prompt_tokens=tokens, schema=GapReport,
        )  # fmt: skip
        refs = References.build(m.id for m in memory)
        warnings = check_references(report.findings(), refs)
        run.result = report.model_dump(mode="json")
        run.warnings = trimmed_warning(inputs.memory_dropped) + warnings
        run.status = RunStatus.COMPLETED
        run.finished_at = now()
    except AppError as exc:  # StepFailed, or a typed gateway error
        await fail(session, run, exc, model)
        exc.details["run_id"] = str(run.id)
        error = exc
    await session.flush()
    logger.info("gap finder run=%s status=%s warnings=%d", run.id, run.status.value,
                len(run.warnings))  # fmt: skip
    return run, error


async def list_gap_runs(
    session: AsyncSession, user_id: uuid.UUID, project_id: uuid.UUID, *, limit: int = 50
) -> list[AgentRun]:
    await get_project(session, user_id, project_id)
    rows = await session.scalars(
        select(AgentRun)
        .where(
            AgentRun.user_id == user_id,
            AgentRun.project_id == project_id,
            AgentRun.run_type == RunType.GAP_FINDER,
        )
        .order_by(AgentRun.created_at.desc(), AgentRun.id.desc())
        .limit(limit)
    )
    return list(rows)
