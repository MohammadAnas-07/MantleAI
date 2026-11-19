"""FastAPI application entry point. Run with: uvicorn app.main:app --reload"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.routing import APIRoute
from sqlalchemy.exc import SQLAlchemyError

from app.api.errors import AllowedHostsMiddleware, JsonOnlyMiddleware, install_error_handlers
from app.api.router import api_router
from app.core.config import settings
from app.core.logging import setup_logging
from app.db.session import SessionLocal, check_database, engine
from app.modules.llm.service import validate_master_key
from app.modules.rag.service import recover_interrupted_runs
from app.modules.workflow.service import check_stage_definitions, recover_interrupted_agent_runs

logger = logging.getLogger(__name__)


async def fail_interrupted_runs() -> None:
    """Index jobs and agent runs run in this process, so none survives a restart. Mark the
    leftovers failed. A database that is down must not stop the API from starting."""
    try:
        async with SessionLocal() as session:
            await recover_interrupted_runs(session)
            await recover_interrupted_agent_runs(session)
            await session.commit()
    except (SQLAlchemyError, OSError) as exc:
        logger.warning("could not check for interrupted runs: %s", type(exc).__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    setup_logging(settings.log_level)
    # Fail fast: without a valid master key, stored provider keys can't be used.
    validate_master_key()
    check_stage_definitions()  # a bad stages.yaml stops the app here
    await fail_interrupted_runs()
    yield
    await engine.dispose()


def operation_id(route: APIRoute) -> str:
    """The route function's name ("list_projects"), so generated API clients get short, stable
    names. tests/test_openapi.py checks they are unique."""
    return route.name


app = FastAPI(
    title="Mantle AI",
    version="0.1.0",
    lifespan=lifespan,
    generate_unique_id_function=operation_id,
)
app.add_middleware(JsonOnlyMiddleware)
# Added after JsonOnly, so it runs first: a preflight is answered before the JSON check, and
# error responses still carry the CORS headers the browser needs to read them.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allowed_origins,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Content-Type"],
    allow_credentials=False,
    max_age=600,
)
# Outermost: a request for a host name we don't serve gets no further.
app.add_middleware(AllowedHostsMiddleware, allowed_hosts=settings.allowed_hosts)
install_error_handlers(app)
app.include_router(api_router)


@app.get("/health", tags=["system"])
async def health() -> dict[str, str]:
    database_up = await check_database()
    return {"status": "ok", "database": "up" if database_up else "down"}
