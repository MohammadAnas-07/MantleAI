"""One agent step: a model call through the gateway, then parse and validate the answer.

An answer that can't be used gets one retry, with the validation error (never the answer) in
the prompt. A second bad answer fails the step. Each attempt writes its own usage row
(purpose agent_run, trigger user: the user started the run). The step row keeps the prompt
version, model, sizes, tokens, cost, latency and the validated output.

Logs hold ids, counts, tokens and timings only: never prompts, memory text or output.
"""

import asyncio
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import AppError
from app.modules.llm.service import (
    ChatMessages,
    Gateway,
    ModelInfo,
    UsageLinks,
    UsagePurpose,
    UsageTrigger,
)
from app.modules.workflow.context import output_reserve
from app.modules.workflow.models import AgentName, AgentRun, AgentRunStep
from app.modules.workflow.outputs import OutputInvalid, parse

logger = logging.getLogger(__name__)

RETRY_NOTE = (
    "Your previous answer could not be used: {error} "
    "Answer again with one JSON object that follows the format exactly."
)


class StepFailed(AppError):
    """A step gave no usable answer (twice invalid, or timed out)."""

    status_code = 502

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message, code=code)


@dataclass
class StepUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: Decimal | None = None

    def add(self, input_tokens: int, output_tokens: int, cost: Decimal | None) -> None:
        """Add one attempt's tokens and cost."""
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens
        if cost is not None:
            self.cost_usd = (self.cost_usd or Decimal(0)) + cost


async def run_step[M: BaseModel](
    session: AsyncSession,
    gateway: Gateway,
    run: AgentRun,
    *,
    agent: AgentName,
    prompt_version: str,
    position: int,
    model: ModelInfo,
    prompt: ChatMessages,
    prompt_tokens: int,
    schema: type[M],
    check: Callable[[M], None] | None = None,
) -> M:
    """Call the model (at most twice), validate, store the step and add its usage to the run.
    Raises StepFailed, or an LLMError from the gateway."""
    usage = StepUsage()
    step = AgentRunStep(
        user_id=run.user_id, run_id=run.id, position=position, agent=agent,
        prompt_version=prompt_version, model_id=model.id, status="failed",
        input_tokens_estimate=prompt_tokens,
    )  # fmt: skip
    started = time.monotonic()
    attempt_prompt = prompt
    try:
        for attempt in (1, 2):
            step.attempts = attempt
            done = await asyncio.wait_for(
                gateway.complete(
                    session, run.user_id, model.id, attempt_prompt,
                    purpose=UsagePurpose.AGENT_RUN, trigger=UsageTrigger.USER,
                    max_tokens=output_reserve(model),
                    links=UsageLinks(project_id=run.project_id, agent_run_id=run.id),
                ),
                timeout=settings.agent_step_timeout_seconds,
            )  # fmt: skip
            usage.add(done.input_tokens, done.output_tokens, done.cost_usd)
            try:
                result = parse(done.text, schema)
                if check is not None:
                    check(result)
            except OutputInvalid as exc:
                logger.warning("agent output invalid run=%s agent=%s attempt=%d",
                               run.id, agent.value, attempt)  # fmt: skip
                if attempt == 2:
                    step.error = "invalid_output"
                    raise StepFailed(
                        "invalid_output",
                        f"The {agent.value} answer was not valid twice: {exc}",
                    ) from None
                attempt_prompt = [
                    *prompt,
                    {"role": "user", "content": RETRY_NOTE.format(error=exc)},
                ]
                continue
            step.status = "succeeded"
            step.output = result.model_dump(mode="json")
            return result
        raise AssertionError("unreachable")
    except TimeoutError:
        step.error = "step_timeout"
        raise StepFailed(
            "step_timeout",
            f"The {agent.value} step took longer than {settings.agent_step_timeout_seconds:g} s.",
        ) from None
    except AppError as exc:
        step.error = step.error or exc.code
        raise
    finally:
        step.input_tokens, step.output_tokens = usage.input_tokens, usage.output_tokens
        step.cost_usd = usage.cost_usd
        step.latency_ms = int((time.monotonic() - started) * 1000)
        session.add(step)
        run.input_tokens += usage.input_tokens
        run.output_tokens += usage.output_tokens
        if usage.cost_usd is not None:
            run.cost_usd = (run.cost_usd or Decimal(0)) + usage.cost_usd
        await session.flush()
        logger.info(
            "agent step run=%s agent=%s status=%s attempts=%d input_tokens=%d "
            "output_tokens=%d ms=%d",
            run.id, agent.value, step.status, step.attempts, usage.input_tokens,
            usage.output_tokens, step.latency_ms,
        )  # fmt: skip
