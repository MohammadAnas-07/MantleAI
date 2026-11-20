"""Agent runs: a small state machine in plain Python, with every step saved in PostgreSQL
(ADR 0004: no LangGraph).

    queued -> running -> (plan)   Planner, Reviewer -> waiting_for_approval -> approved | rejected
                      -> (review) Reviewer          -> completed
    any step can end in failed; an accepted cancel always ends in cancelled.

The job and the cancel endpoint run at the same time, so every status change is a conditional
UPDATE that only moves from the expected status: the job claims a run only while it is queued,
and writes its final status only while the run is running and nobody asked to cancel. The cancel
flag is also checked before every model call and before each result is saved.

The user starts a run; it then executes as an in-process background task and is polled by
status. The run commits after each step, so a poll shows progress and a crash loses at most the
step in flight. At startup, runs left queued or running are marked failed ("interrupted");
runs waiting for approval stay as they are. Agents have no tools and nothing they produce is
saved to memory here: that needs the user's approval (approval.py).
"""

import logging
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import AppError, NotFound
from app.core.repositories import UserRepository
from app.modules.llm.service import ChatMessages, Gateway, LLMError, ModelInfo, UsageLinks
from app.modules.projects.service import MemoryRef, get_project, memory_refs
from app.modules.rag.service import retrieve_for_context
from app.modules.workflow.context import (
    AgentInputs,
    check_fits,
    code_text,
    load_memory,
    messages,
    output_reserve,
    plan_text,
    project_text,
    requirement_text,
    stage_text,
)
from app.modules.workflow.models import (
    ACTIVE_RUN_STATUSES,
    AgentName,
    AgentRun,
    RunStatus,
    RunType,
)
from app.modules.workflow.outputs import (
    Plan,
    References,
    Review,
    check_plan,
    check_references,
    flag_duplicates,
)
from app.modules.workflow.prompts import PLANNER_PROMPT, REVIEWER_PROMPT, load_prompt
from app.modules.workflow.run_setup import (
    chat_model_with_key,
    check_cost,
    create_run,
    error_fields,
    estimate,
    get_run,
    now,
)
from app.modules.workflow.state import StageView, current_stage, view
from app.modules.workflow.steps import RunCancelled, run_step

logger = logging.getLogger(__name__)

# Upper bound for code context in the estimate: blocks x the largest segment (~4 chars/token).
_CODE_TOKENS_PER_BLOCK = settings.chunk_max_chars // 4 + 50


def planner_system_prompt() -> str:
    """The Planner prompt file with its limits filled in (no str.format: the file has JSON)."""
    return (
        load_prompt(PLANNER_PROMPT)
        .replace("{max_items}", str(settings.agent_plan_max_items))
        .replace("{title_max}", str(settings.memory_title_max_length))
    )


# ---- inputs --------------------------------------------------------------------------------


def _requirement(
    memory: list[MemoryRef], requirement_id: str | None, text: str | None
) -> str | None:
    if requirement_id is None:
        return text
    item = next((m for m in memory if str(m.id) == requirement_id), None)
    if item is None or item.kind != "requirement":
        raise NotFound("Requirement not found in this project.")
    return item.title + (f"\n\n{item.body}" if item.body else "")


async def _inputs(
    session: AsyncSession,
    gateway: Gateway,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
    model: ModelInfo,
    stage: StageView,
    run_input: dict[str, Any],
) -> AgentInputs:
    project = await get_project(session, user_id, project_id)
    memory = await memory_refs(session, user_id, project_id)
    inputs = AgentInputs(project=project, stage=stage, memory=memory)
    inputs.requirement = _requirement(
        memory, run_input.get("requirement_id"), run_input.get("requirement_text")
    )
    await load_memory(session, gateway, user_id, project_id, model, inputs)
    return inputs


def _base_sections(inputs: AgentInputs) -> list[str]:
    sections = [project_text(inputs.project, inputs.memory), stage_text(inputs.stage),
                inputs.memory_text]  # fmt: skip
    if inputs.requirement:
        sections.append(requirement_text(inputs.requirement))
    sections.append(code_text(inputs.code))
    return sections


def planner_prompt(inputs: AgentInputs) -> ChatMessages:
    """System prompt and data for the Planner."""
    return messages(planner_system_prompt(), _base_sections(inputs))


def reviewer_prompt(inputs: AgentInputs, plan: Plan | None) -> ChatMessages:
    """System prompt and data for the Reviewer, with the plan when there is one."""
    sections = _base_sections(inputs)
    if plan is not None:
        sections.append(plan_text(plan))
    return messages(load_prompt(REVIEWER_PROMPT), sections)


# ---- start ---------------------------------------------------------------------------------


@dataclass
class PreparedRun:
    """What a start needs after the checks: the model, the stage, the stored input and the
    estimate."""

    model: ModelInfo
    stage: StageView
    run_input: dict[str, Any]
    prompt_version: str
    estimate: dict[str, Any]


async def prepare_run(
    session: AsyncSession,
    gateway: Gateway,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
    *,
    run_type: RunType,
    model_id: uuid.UUID,
    requirement_id: uuid.UUID | None = None,
    requirement_text: str | None = None,
    use_code_context: bool = False,
    force: bool = False,
) -> PreparedRun:
    """Every check a start makes except the cost guard and the one-active-run rule, and the
    estimate. No model call (prompts are only counted).

    404 for another user's project or an unknown requirement; 422 without a key; 413 when the
    prompt doesn't fit (with suggested models).
    """
    await get_project(session, user_id, project_id)
    model = await chat_model_with_key(session, user_id, model_id)
    stage = await current_stage(session, user_id, project_id)
    run_input: dict[str, Any] = {
        "requirement_id": str(requirement_id) if requirement_id else None,
        "requirement_text": requirement_text,
        "use_code_context": use_code_context,
        "force": force,
    }
    inputs = await _inputs(session, gateway, user_id, project_id, model, stage, run_input)
    code_tokens = _CODE_TOKENS_PER_BLOCK * settings.agent_code_context_max_blocks
    code_tokens = code_tokens if use_code_context else 0
    if run_type == RunType.PLAN:
        first = await check_fits(session, gateway, user_id, model, planner_prompt(inputs))
        # The Reviewer sees the same data plus the plan (at most one output reserve).
        steps = [first + code_tokens, first + code_tokens + output_reserve(model)]
        prompt_version = f"{PLANNER_PROMPT},{REVIEWER_PROMPT}"
    else:
        first = await check_fits(session, gateway, user_id, model, reviewer_prompt(inputs, None))
        steps = [first + code_tokens]
        prompt_version = REVIEWER_PROMPT
    return PreparedRun(model, stage, run_input, prompt_version, estimate(model, steps))


async def start_run(
    session: AsyncSession,
    gateway: Gateway,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
    *,
    run_type: RunType,
    model_id: uuid.UUID,
    requirement_id: uuid.UUID | None = None,
    requirement_text: str | None = None,
    use_code_context: bool = False,
    force: bool = False,
) -> AgentRun:
    """Check everything and create a queued run; the caller commits and starts the job.

    Raises what `prepare_run` raises, and 409 when a run is active or the estimate is over
    AGENT_RUN_COST_LIMIT_USD without force (422 model_not_priced without prices). No model
    call happens here.
    """
    prepared = await prepare_run(
        session, gateway, user_id, project_id, run_type=run_type, model_id=model_id,
        requirement_id=requirement_id, requirement_text=requirement_text,
        use_code_context=use_code_context, force=force,
    )  # fmt: skip
    check_cost(prepared.estimate, force)
    run = await create_run(
        session, user_id=user_id, project_id=project_id, run_type=run_type,
        status=RunStatus.QUEUED, model=prepared.model, stage_id=prepared.stage.definition.id,
        prompt_version=prepared.prompt_version, run_input=prepared.run_input,
        run_estimate=prepared.estimate,
    )  # fmt: skip
    logger.info("agent run queued run=%s type=%s project=%s", run.id, run_type.value, project_id)
    return run


# ---- the job -------------------------------------------------------------------------------


async def _check_cancel(session: AsyncSession, run: AgentRun) -> None:
    """Raise RunCancelled if the user asked to cancel. Reads the database, not the session's
    copy of the run."""
    requested = await session.scalar(
        select(AgentRun.cancel_requested_at).where(
            AgentRun.user_id == run.user_id, AgentRun.id == run.id
        )
    )
    if requested is not None:
        raise RunCancelled


def _conditional(run: AgentRun, *, expect: RunStatus) -> Any:
    """An UPDATE of this run that matches only while it has status `expect`."""
    return (
        update(AgentRun)
        .where(AgentRun.user_id == run.user_id, AgentRun.id == run.id, AgentRun.status == expect)
        .execution_options(synchronize_session=False)
    )


async def _finish(session: AsyncSession, run: AgentRun, to: RunStatus, **values: Any) -> None:
    """Write the final status of a running run. If a cancel was accepted meanwhile, the run
    ends cancelled instead, whatever `to` was. Commits."""
    await session.flush()  # results, tokens and warnings first; they never touch the status
    stamp = {} if to == RunStatus.WAITING_FOR_APPROVAL else {"finished_at": now()}
    result = await session.execute(
        _conditional(run, expect=RunStatus.RUNNING)
        .where(AgentRun.cancel_requested_at.is_(None))
        .values(status=to, **stamp, **values)
    )
    if result.rowcount != 1:
        await session.execute(
            _conditional(run, expect=RunStatus.RUNNING).values(
                status=RunStatus.CANCELLED, finished_at=now()
            )
        )
    await session.commit()
    await session.refresh(run)


async def _stage_of(session: AsyncSession, user_id: uuid.UUID, run: AgentRun) -> StageView:
    state = await view(session, user_id, run.project_id, events=False)
    found = next((s for s in state.stages if s.definition.id == run.stage_id), None)
    return found or state.current or state.stages[-1]


async def _code_context(
    session: AsyncSession, gateway: Gateway, run: AgentRun, inputs: AgentInputs
) -> None:
    """Up to AGENT_CODE_CONTEXT_MAX_BLOCKS code blocks for the requirement. The query embedding
    is logged with purpose "embedding". A failure only adds a warning."""
    if not run.input.get("use_code_context") or not inputs.requirement:
        return
    links = UsageLinks(project_id=run.project_id, agent_run_id=run.id)
    try:
        async with session.begin_nested():
            try:
                outcome = await retrieve_for_context(
                    session, gateway, run.user_id, run.project_id, inputs.requirement, links,
                    top_k=settings.agent_code_context_max_blocks,
                )  # fmt: skip
            except LLMError as exc:
                run.warnings = [*run.warnings, {"code": "code_context_failed",
                                                "error_code": exc.code}]  # fmt: skip
                return
    except Exception as exc:
        logger.warning("code context failed run=%s type=%s", run.id, type(exc).__name__)
        run.warnings = [*run.warnings, {"code": "code_context_failed"}]
        return
    inputs.code = outcome.blocks[: settings.agent_code_context_max_blocks]
    if outcome.warning:
        run.warnings = [*run.warnings, outcome.warning]


def _existing_tasks(memory: list[MemoryRef]) -> dict[str, uuid.UUID]:
    return {m.title.casefold(): m.id for m in memory if m.kind == "task"}


async def _execute(
    session: AsyncSession, gateway: Gateway, run: AgentRun, model: ModelInfo
) -> RunStatus:
    """Run the steps and return the status the run should end in. Never writes the status;
    raises RunCancelled when the user cancelled."""
    user_id = run.user_id

    async def check_cancel() -> None:
        await _check_cancel(session, run)

    await check_cancel()
    stage = await _stage_of(session, user_id, run)
    inputs = await _inputs(session, gateway, user_id, run.project_id, model, stage, run.input)
    if inputs.memory_dropped:
        run.warnings = [*run.warnings, {"code": "memory_trimmed", "count": inputs.memory_dropped}]
    await _code_context(session, gateway, run, inputs)
    memory_ids = [m.id for m in inputs.memory]

    plan: Plan | None = None
    position = 0
    if run.run_type == RunType.PLAN:
        prompt = planner_prompt(inputs)
        tokens = await check_fits(session, gateway, user_id, model, prompt)
        plan = await run_step(
            session, gateway, run, agent=AgentName.PLANNER, prompt_version=PLANNER_PROMPT,
            position=position, model=model, prompt=prompt, prompt_tokens=tokens, schema=Plan,
            check=check_plan, before_call=check_cancel,
        )  # fmt: skip
        flag_duplicates(plan, _existing_tasks(inputs.memory))
        await check_cancel()
        run.result = {"plan": plan.model_dump(mode="json")}
        await session.commit()
        position += 1

    prompt = reviewer_prompt(inputs, plan)
    tokens = await check_fits(session, gateway, user_id, model, prompt)
    review = await run_step(
        session, gateway, run, agent=AgentName.REVIEWER, prompt_version=REVIEWER_PROMPT,
        position=position, model=model, prompt=prompt, prompt_tokens=tokens, schema=Review,
        before_call=check_cancel,
    )  # fmt: skip
    refs = References.build(memory_ids, plan)
    warnings = check_references((("findings", f) for f in review.findings), refs)
    await check_cancel()
    run.warnings = [*run.warnings, *warnings]
    run.result = {**run.result, "review": review.model_dump(mode="json")}
    return RunStatus.WAITING_FOR_APPROVAL if run.run_type == RunType.PLAN else RunStatus.COMPLETED


async def run_agent_job(
    session_factory: Any, gateway: Gateway, user_id: uuid.UUID, run_id: uuid.UUID
) -> None:
    """The background task. Never raises: the outcome is stored on the run (rule 55)."""
    async with session_factory() as session:
        claimed = await session.execute(
            update(AgentRun)
            .where(AgentRun.user_id == user_id, AgentRun.id == run_id,
                   AgentRun.status == RunStatus.QUEUED)
            .values(status=RunStatus.RUNNING, started_at=now())
            .execution_options(synchronize_session=False)
        )  # fmt: skip
        await session.commit()
        if claimed.rowcount != 1:
            return  # cancelled before it started, or already picked up
        run = await session.scalar(
            select(AgentRun)
            .where(AgentRun.user_id == user_id, AgentRun.id == run_id)
            .execution_options(populate_existing=True)
        )
        assert run is not None
        model: ModelInfo | None = None
        try:
            model = await chat_model_with_key(session, user_id, run.model_id)
            final = await _execute(session, gateway, run, model)
            await _finish(session, run, final)
        except RunCancelled:
            await _finish(session, run, RunStatus.CANCELLED)
        except AppError as exc:  # a failed step or a typed gateway error
            fields = await error_fields(session, user_id, exc, model)
            await _finish(session, run, RunStatus.FAILED, **fields)
        except Exception as exc:
            # Type only: a message could quote memory text or model output.
            logger.error("agent run crashed run=%s type=%s", run_id, type(exc).__name__)
            await session.rollback()
            await session.refresh(run)  # the rollback expired it
            await _finish(session, run, RunStatus.FAILED, error="internal_error",
                          error_message="The run stopped on an internal error.")  # fmt: skip
        logger.info("agent run finished run=%s status=%s input_tokens=%d output_tokens=%d",
                    run_id, RunStatus(run.status).value,
                    run.input_tokens, run.output_tokens)  # fmt: skip


# ---- cancel, read, recover -----------------------------------------------------------------


async def request_cancel(session: AsyncSession, user_id: uuid.UUID, run_id: uuid.UUID) -> AgentRun:
    """Queued: cancelled now. Running: the job stops at its next check and ends cancelled.
    Anything else (finished, waiting for approval) is 409, and so is a gap finder run: it runs
    inside its own request and can't be stopped. Both updates are conditional, so a cancel never
    overwrites a status the job wrote meanwhile."""
    run = await get_run(session, user_id, run_id)
    if run.run_type == RunType.GAP_FINDER:
        raise AppError("A gap finder run can't be cancelled.", code="agent_run_not_cancellable",
                       status_code=409)  # fmt: skip
    stamp = now()
    queued = await session.execute(
        _conditional(run, expect=RunStatus.QUEUED).values(
            status=RunStatus.CANCELLED, finished_at=stamp, cancel_requested_at=stamp
        )
    )
    if queued.rowcount != 1:
        running = await session.execute(
            _conditional(run, expect=RunStatus.RUNNING).values(cancel_requested_at=stamp)
        )
        if running.rowcount != 1:
            await session.refresh(run)
            raise AppError(f"A run that is {run.status} can't be cancelled.",
                           code="agent_run_not_active", status_code=409)  # fmt: skip
    await session.refresh(run)
    return run


async def list_runs(
    session: AsyncSession,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
    *,
    limit: int = 50,
) -> list[AgentRun]:
    """Plan and review runs of the project, newest first (gap finder runs are listed apart)."""
    await get_project(session, user_id, project_id)
    rows = await session.scalars(
        select(AgentRun)
        .where(
            AgentRun.user_id == user_id,
            AgentRun.project_id == project_id,
            AgentRun.run_type.in_([RunType.PLAN, RunType.REVIEW]),
        )
        .order_by(AgentRun.created_at.desc(), AgentRun.id.desc())
        .limit(limit)
    )
    return list(rows)


async def recover_interrupted_runs(session: AsyncSession) -> int:
    """At startup: a run still queued or running died with the old process, so it is marked
    failed ("interrupted"). Runs waiting for approval keep their drafts. The caller commits."""
    users = await UserRepository(session).list(limit=10_000)
    changed = 0
    for user in users:
        result = await session.execute(
            update(AgentRun)
            .where(AgentRun.user_id == user.id, AgentRun.status.in_(ACTIVE_RUN_STATUSES))
            .values(
                status=RunStatus.FAILED,
                error="interrupted",
                finished_at=now(),
                error_message="The server stopped while this run was in progress.",
            )  # fmt: skip
        )
        changed += result.rowcount or 0
    if changed:
        logger.warning("marked %d interrupted agent runs as failed", changed)
    return changed
