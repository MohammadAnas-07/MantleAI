"""All /api/v1 routes (rule 25)."""

from fastapi import APIRouter

from app.api import projects, system
from app.modules.conversations import router as conversations
from app.modules.llm import router as llm
from app.modules.projects import router as project_memory
from app.modules.rag import router as rag
from app.modules.workflow import router as workflow

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(system.router)
api_router.include_router(llm.router)
api_router.include_router(projects.router)
api_router.include_router(project_memory.router)
api_router.include_router(conversations.router)
api_router.include_router(rag.router)
api_router.include_router(workflow.router)
