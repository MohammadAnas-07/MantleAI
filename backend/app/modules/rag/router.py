"""Indexing and search endpoints (docs/api-outline.md, "RAG"). Routes stay thin; the rules are
in the rag service."""

import uuid
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Query, Response

from app.api.deps import CurrentUserId, DbSession, SessionFactoryDep
from app.core.config import settings
from app.core.errors import NotFound
from app.modules.llm.service import Gateway, get_gateway
from app.modules.rag import service
from app.modules.rag.models import DocumentStatus
from app.modules.rag.schemas import (
    DocumentOut,
    DocumentPageOut,
    EmptyIn,
    IndexStartIn,
    IndexStatusOut,
    RunOut,
    RunStarted,
    SearchHitOut,
    SearchIn,
    SearchOut,
    SourceIn,
)

router = APIRouter(tags=["rag"])

GatewayDep = Annotated[Gateway, Depends(get_gateway)]


def status_out(status: service.IndexStatus) -> IndexStatusOut:
    return IndexStatusOut(
        project_id=status.project_id,
        root_path=status.root_path,
        indexed=status.indexed,
        last_indexed_at=status.last_indexed_at,
        needs_reindex=status.needs_reindex,
        reindex_reasons=list(status.reindex_reasons),
        embedding_models=list(status.embedding_models),
        files=status.files,
        active_run_id=status.active_run_id,
    )


@router.put("/projects/{project_id}/source")
async def set_source(
    project_id: uuid.UUID, body: SourceIn, session: DbSession, user_id: CurrentUserId
) -> IndexStatusOut:
    """Set or change the folder to index. A new folder needs an explicit re-index."""
    status = await service.set_source(session, user_id, project_id, body.root_path)
    await session.commit()
    return status_out(status)


@router.get("/projects/{project_id}/index")
async def get_index_status(
    project_id: uuid.UUID, session: DbSession, user_id: CurrentUserId
) -> IndexStatusOut:
    return status_out(await service.index_status(session, user_id, project_id))


@router.post("/projects/{project_id}/index/estimate")
async def estimate(
    project_id: uuid.UUID, body: EmptyIn, session: DbSession, user_id: CurrentUserId
) -> dict[str, object]:
    """What indexing would do and cost now. Reads the folder; no model call."""
    return (await service.estimate_index(session, user_id, project_id)).as_dict()


@router.post("/projects/{project_id}/index", status_code=202)
async def start_index(
    project_id: uuid.UUID,
    body: IndexStartIn,
    background: BackgroundTasks,
    session: DbSession,
    user_id: CurrentUserId,
    gateway: GatewayDep,
    session_factory: SessionFactoryDep,
) -> RunStarted:
    """Start (re-)indexing in the background. 409 if a run is active or the estimate is over
    the cost limit without force; 422 without a folder, embedding model or key."""
    run = await service.start_index(session, user_id, project_id, force=body.force)
    await session.commit()
    background.add_task(service.run_index_job, session_factory, gateway, user_id, run.id)
    return RunStarted(run_id=run.id, status=run.status, estimate=run.estimate)


@router.delete("/projects/{project_id}/index", status_code=204)
async def delete_index(
    project_id: uuid.UUID, session: DbSession, user_id: CurrentUserId
) -> Response:
    await service.delete_index(session, user_id, project_id)
    await session.commit()
    return Response(status_code=204)


@router.get("/projects/{project_id}/index-runs")
async def list_runs(
    project_id: uuid.UUID,
    session: DbSession,
    user_id: CurrentUserId,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[RunOut]:
    rows = await service.list_runs(session, user_id, project_id, limit)
    return [RunOut.model_validate(r) for r in rows]


@router.get("/index-runs/{run_id}")
async def get_run(run_id: uuid.UUID, session: DbSession, user_id: CurrentUserId) -> RunOut:
    return RunOut.model_validate(await service.get_run(session, user_id, run_id))


@router.post("/index-runs/{run_id}/cancel")
async def cancel_run(
    run_id: uuid.UUID, body: EmptyIn, session: DbSession, user_id: CurrentUserId
) -> RunOut:
    """A queued run stops now; a running one stops before its next batch."""
    run = await service.cancel_run(session, user_id, run_id)
    await session.commit()
    return RunOut.model_validate(run)


@router.get("/projects/{project_id}/documents")
async def list_documents(
    project_id: uuid.UUID,
    session: DbSession,
    user_id: CurrentUserId,
    status: DocumentStatus | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> DocumentPageOut:
    """Indexed and skipped files, with the reason a file was skipped."""
    page = await service.list_documents(
        session, user_id, project_id, status=status, limit=limit, offset=offset
    )
    return DocumentPageOut(
        items=[DocumentOut.model_validate(d) for d in page.items],
        total=page.total,
        limit=limit,
        offset=offset,
        counts=page.counts,
    )


@router.post("/projects/{project_id}/search", tags=["dev"])
async def search(
    project_id: uuid.UUID,
    body: SearchIn,
    session: DbSession,
    user_id: CurrentUserId,
    gateway: GatewayDep,
) -> SearchOut:
    """Dev-only: test retrieval. Embeds the query (purpose "embedding") and returns the
    merged results with their vector rank, text rank and fused score. 404 unless
    APP_ENV=development."""
    if settings.app_env != "development":
        raise NotFound("Not found.")
    result = await service.search(
        session, gateway, user_id, project_id, body.query,
        top_k=body.top_k, mode=body.mode, path_prefix=body.path_prefix, language=body.language,
    )  # fmt: skip
    await session.commit()  # keep the usage row of the query embedding
    return SearchOut(
        results=[
            SearchHitOut(
                path=b.path,
                start_line=b.start_line,
                end_line=b.end_line,
                language=b.language,
                symbol=b.symbol,
                vector_rank=b.vector_rank,
                text_rank=b.text_rank,
                score=b.score,
                chunk_ids=list(b.chunk_ids),
                text=b.text,
            )
            for b in result.blocks
        ],  # fmt: skip
        needs_reindex=result.needs_reindex,
        reindex_reasons=list(result.reindex_reasons),
    )
