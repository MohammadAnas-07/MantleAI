"""Public interface of the workflow module (rule 6). The app uses only this file."""

from app.modules.workflow.stages import StageConfigError, StageList, get_stages, load_stages

__all__ = ["StageConfigError", "StageList", "check_stage_definitions", "load_stages"]


def check_stage_definitions() -> StageList:
    """Load and check stages.yaml. Called at startup: a bad file stops the app with a message
    (StageConfigError) instead of failing later in a request."""
    return get_stages()
