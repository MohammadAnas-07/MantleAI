"""Repositories for the workflow module. Every query filters by user_id."""

from app.db.repository import UserScopedRepository
from app.modules.workflow.models import AgentRun, StageState, WorkflowRun


class WorkflowRunRepository(UserScopedRepository[WorkflowRun]):
    model = WorkflowRun


class StageStateRepository(UserScopedRepository[StageState]):
    model = StageState


class AgentRunRepository(UserScopedRepository[AgentRun]):
    model = AgentRun
