"""Public interface of the workflow module (rule 6). The app uses only this file."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.workflow.runs import recover_interrupted_runs
from app.modules.workflow.stages import StageConfigError, StageList, get_stages, load_stages

__all__ = [
    "StageConfigError",
    "StageList",
    "check_stage_definitions",
    "load_stages",
    "recover_interrupted_agent_runs",
]


def check_stage_definitions() -> StageList:
    """Load and check stages.yaml. Called at startup: a bad file stops the app with a message
    (StageConfigError) instead of failing later in a request."""
    return get_stages()


async def recover_interrupted_agent_runs(session: AsyncSession) -> int:
    """At startup: queued or running agent runs become failed ("interrupted"); runs waiting
    for approval stay. The caller commits."""
    return await recover_interrupted_runs(session)
