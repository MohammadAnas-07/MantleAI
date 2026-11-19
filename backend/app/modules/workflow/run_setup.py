"""Shared by gap finder and agent runs: model and key checks, the cost estimate and guard,
creating the run row (one active run per project), and storing a failure."""

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import AppError, NotFound
from app.modules.llm.service import (
    ModelInfo,
    NoCredential,
    get_chat_model,
    providers_with_keys,
    suggest_models,
)
from app.modules.workflow.context import output_reserve
from app.modules.workflow.models import ACTIVE_RUN_STATUSES, AgentRun, RunStatus, RunType

_MTOK = Decimal(1_000_000)
# Errors that come with "switch to one of these models" suggestions.
_SUGGEST_FOR = {"context_too_long", "rate_limited", "quota_exhausted"}


def now() -> datetime:
    """The current time in UTC."""
    return datetime.now(UTC)


async def chat_model_with_key(
    session: AsyncSession, user_id: uuid.UUID, model_id: uuid.UUID
) -> ModelInfo:
    """An enabled chat model the user has a key for; 422 otherwise."""
    model = await get_chat_model(session, model_id)
    if model.provider not in await providers_with_keys(session, user_id):
        raise NoCredential(
            f"Add an API key for {model.provider} to use {model.display_name}.",
            details={"provider": model.provider},
        )
    return model


def estimate(model: ModelInfo, prompt_tokens: list[int]) -> dict[str, Any]:
    """Tokens and cost if every step uses its whole output reserve (an upper bound)."""
    reserve = output_reserve(model)
    input_tokens = sum(prompt_tokens)
    output_tokens = reserve * len(prompt_tokens)
    cost: Decimal | None = None
    if model.input_cost_per_mtok is not None and model.output_cost_per_mtok is not None:
        cost = (
            Decimal(input_tokens) * model.input_cost_per_mtok
            + Decimal(output_tokens) * model.output_cost_per_mtok
        ) / _MTOK
        cost = cost.quantize(Decimal("0.000001"))
    return {
        "steps": len(prompt_tokens),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost_usd": str(cost) if cost is not None else None,
        "cost_limit_usd": str(settings.agent_run_cost_limit_usd),
        "model": model.litellm_model,
    }


def check_cost(run_estimate: dict[str, Any], force: bool) -> None:
    """409 cost_limit_exceeded when the estimate is over the limit and force is off."""
    cost = run_estimate["cost_usd"]
    if force or cost is None or Decimal(cost) <= settings.agent_run_cost_limit_usd:
        return
    raise AppError(
        f"This run could cost about ${cost}, above the limit of "
        f"${settings.agent_run_cost_limit_usd}. Send force=true to run it anyway.",
        code="cost_limit_exceeded",
        status_code=409,
        details={"estimate": run_estimate},
    )


async def active_run(
    session: AsyncSession, user_id: uuid.UUID, project_id: uuid.UUID
) -> AgentRun | None:
    """The project's queued or running run, if any."""
    return await session.scalar(
        select(AgentRun).where(
            AgentRun.user_id == user_id,
            AgentRun.project_id == project_id,
            AgentRun.status.in_(ACTIVE_RUN_STATUSES),
        )
    )


def _in_progress() -> AppError:
    return AppError("This project already has an agent run in progress.",
                    code="agent_run_in_progress", status_code=409)  # fmt: skip


async def create_run(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
    run_type: RunType,
    status: RunStatus,
    model: ModelInfo,
    stage_id: str,
    prompt_version: str,
    run_input: dict[str, Any],
    run_estimate: dict[str, Any],
) -> AgentRun:
    """Insert the run. 409 agent_run_in_progress when another run of the project is queued or
    running (a partial unique index makes that true even for two requests at once)."""
    if await active_run(session, user_id, project_id) is not None:
        raise _in_progress()
    run = AgentRun(
        user_id=user_id, project_id=project_id, run_type=run_type, status=status,
        stage_id=stage_id, model_id=model.id, prompt_version=prompt_version, input=run_input,
        estimate=run_estimate, started_at=now() if status == RunStatus.RUNNING else None,
    )  # fmt: skip
    session.add(run)
    try:
        async with session.begin_nested():
            await session.flush()
    except IntegrityError:
        raise _in_progress() from None
    return run


async def fail(
    session: AsyncSession, run: AgentRun, error: AppError, model: ModelInfo | None
) -> None:
    """Store why the run failed. Rate limit and context errors carry suggested models."""
    details = dict(error.details)
    if model is not None and error.code in _SUGGEST_FOR and "suggested_models" not in details:
        details["suggested_models"] = await suggest_models(session, run.user_id, model, error.code)
        error.details["suggested_models"] = details["suggested_models"]
    run.status = RunStatus.FAILED
    run.error, run.error_message, run.error_details = error.code, error.message, details
    run.finished_at = now()


async def get_run(session: AsyncSession, user_id: uuid.UUID, run_id: uuid.UUID) -> AgentRun:
    """One of the user's runs; 404 for another user's run."""
    run = await session.scalar(
        select(AgentRun).where(AgentRun.user_id == user_id, AgentRun.id == run_id)
    )
    if run is None:
        raise NotFound("Agent run not found.")
    return run
