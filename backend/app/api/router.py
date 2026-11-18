"""All /api/v1 routes (rule 25)."""

from fastapi import APIRouter

from app.api import system
from app.modules.llm import router as llm

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(system.router)
api_router.include_router(llm.router)
