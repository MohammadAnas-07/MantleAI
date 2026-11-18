"""FastAPI application entry point. Run with: uvicorn app.main:app --reload"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.errors import JsonOnlyMiddleware, install_error_handlers
from app.api.router import api_router
from app.core.config import settings
from app.core.logging import setup_logging
from app.db.session import check_database, engine
from app.modules.llm.service import validate_master_key


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    setup_logging(settings.log_level)
    # Fail fast: without a valid master key, stored provider keys can't be used.
    validate_master_key()
    yield
    await engine.dispose()


app = FastAPI(title="Mantle AI", version="0.1.0", lifespan=lifespan)
app.add_middleware(JsonOnlyMiddleware)
install_error_handlers(app)
app.include_router(api_router)


@app.get("/health")
async def health() -> dict[str, str]:
    database_up = await check_database()
    return {"status": "ok", "database": "up" if database_up else "down"}
