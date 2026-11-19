"""Repositories for the workflow module. Every query filters by user_id."""

from app.db.repository import UserScopedRepository
from app.modules.workflow.models import AgentRun, AgentRunStep, ProjectWorkflow, WorkflowEvent


class ProjectWorkflowRepository(UserScopedRepository[ProjectWorkflow]):
    model = ProjectWorkflow


class WorkflowEventRepository(UserScopedRepository[WorkflowEvent]):
    model = WorkflowEvent


class AgentRunRepository(UserScopedRepository[AgentRun]):
    model = AgentRun


class AgentRunStepRepository(UserScopedRepository[AgentRunStep]):
    model = AgentRunStep
