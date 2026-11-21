"""API views of runs. The steps of every run in a list come from one query, not one per run
(audit A-013)."""

from collections import defaultdict
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.workflow.models import AgentRun, AgentRunStep
from app.modules.workflow.schemas import AgentRunOut, AgentRunStepOut


async def runs_out(session: AsyncSession, runs: Sequence[AgentRun]) -> list[AgentRunOut]:
    """Full views of `runs` (all of one user), with their steps in order."""
    if not runs:
        return []
    rows = await session.scalars(
        select(AgentRunStep)
        .where(
            AgentRunStep.user_id == runs[0].user_id,
            AgentRunStep.run_id.in_([r.id for r in runs]),
        )
        .order_by(AgentRunStep.run_id, AgentRunStep.position)
    )
    steps: dict[object, list[AgentRunStepOut]] = defaultdict(list)
    for step in rows:
        steps[step.run_id].append(AgentRunStepOut.model_validate(step))
    out = []
    for run in runs:
        view = AgentRunOut.model_validate(run)
        view.steps = steps.get(run.id, [])
        out.append(view)
    return out


async def run_out(session: AsyncSession, run: AgentRun) -> AgentRunOut:
    """The full view of one run, with its steps."""
    [view] = await runs_out(session, [run])
    return view
