"""Conversation endpoints (docs/api-outline.md, "Conversations and model switching")."""

import json
import uuid
from collections.abc import AsyncIterator
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Response
from fastapi.responses import StreamingResponse
from starlette.background import BackgroundTask

from app.api.deps import CurrentUserId, DbSession, SessionFactoryDep
from app.modules.conversations import service
from app.modules.conversations.models import Conversation, HandoffReason
from app.modules.conversations.repository import (
    ContextHandoffRepository,
    ConversationRepository,
    ConversationSummaryRepository,
)
from app.modules.conversations.schemas import (
    ConversationCreate,
    ConversationOut,
    ConversationRename,
    HandoffOut,
    MessageCreate,
    MessageOut,
    SummaryOut,
    SwitchModelIn,
    SwitchOut,
)
from app.modules.conversations.summary import run_rolling_summary
from app.modules.llm.service import Gateway, get_gateway

router = APIRouter(tags=["conversations"])

GatewayDep = Annotated[Gateway, Depends(get_gateway)]


def _out(conversation: Conversation) -> ConversationOut:
    return ConversationOut(
        id=conversation.id,
        project_id=conversation.project_id,
        title=conversation.title,
        current_model_id=conversation.current_model_id,
        generating=conversation.generating_since is not None,
        summary_error=conversation.summary_error,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
    )


@router.get("/projects/{project_id}/conversations")
async def list_conversations(
    project_id: uuid.UUID, session: DbSession, user_id: CurrentUserId
) -> list[ConversationOut]:
    rows = await service.list_conversations(session, user_id, project_id)
    return [_out(c) for c in rows]


@router.post("/projects/{project_id}/conversations", status_code=201)
async def create_conversation(
    project_id: uuid.UUID, body: ConversationCreate, session: DbSession, user_id: CurrentUserId
) -> ConversationOut:
    conversation = await service.create_conversation(
        session, user_id, project_id, body.model_id, body.title
    )
    await session.commit()
    return _out(conversation)


@router.get("/conversations/{conversation_id}")
async def get_conversation(
    conversation_id: uuid.UUID, session: DbSession, user_id: CurrentUserId
) -> ConversationOut:
    return _out(await service.get_conversation(session, user_id, conversation_id))


@router.patch("/conversations/{conversation_id}")
async def rename_conversation(
    conversation_id: uuid.UUID, body: ConversationRename, session: DbSession, user_id: CurrentUserId
) -> ConversationOut:
    conversation = await service.get_conversation(session, user_id, conversation_id)
    conversation.title = body.title
    await session.commit()
    await session.refresh(conversation)
    return _out(conversation)


@router.delete("/conversations/{conversation_id}", status_code=204)
async def delete_conversation(
    conversation_id: uuid.UUID, session: DbSession, user_id: CurrentUserId
) -> Response:
    await service.get_conversation(session, user_id, conversation_id)
    await ConversationRepository(session, user_id).delete(conversation_id)
    await session.commit()
    return Response(status_code=204)


@router.get("/conversations/{conversation_id}/messages")
async def list_messages(
    conversation_id: uuid.UUID,
    session: DbSession,
    user_id: CurrentUserId,
    after_sequence: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[MessageOut]:
    rows = await service.list_messages(session, user_id, conversation_id, after_sequence, limit)
    return [MessageOut.model_validate(m) for m in rows]


def _sse(event: service.SseEvent) -> str:
    return f"event: {event.event}\ndata: {json.dumps(event.data)}\n\n"


@router.post(
    "/conversations/{conversation_id}/messages",
    response_class=StreamingResponse,
    responses={200: {"content": {"text/event-stream": {}}}},
)
async def send_message(
    conversation_id: uuid.UUID,
    body: MessageCreate,
    session: DbSession,
    user_id: CurrentUserId,
    gateway: GatewayDep,
    session_factory: SessionFactoryDep,
) -> StreamingResponse:
    """Send a message; the reply streams as SSE: message_start, delta..., message_end | error."""
    prepared = await service.prepare_reply(session, gateway, user_id, conversation_id, body.content)
    events = service.stream_reply(session_factory, gateway, user_id, prepared)

    async def body_stream() -> AsyncIterator[str]:
        async for event in events:
            yield _sse(event)

    # After the reply: the rolling summary, only if it's on and the threshold is passed.
    background = BackgroundTask(
        run_rolling_summary, session_factory, gateway, user_id, conversation_id
    )
    return StreamingResponse(
        body_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        background=background,
    )


@router.get("/conversations/{conversation_id}/summary")
async def get_summary(
    conversation_id: uuid.UUID, session: DbSession, user_id: CurrentUserId
) -> SummaryOut:
    conversation = await service.get_conversation(session, user_id, conversation_id)
    row = await ConversationSummaryRepository(session, user_id).latest(conversation_id)
    return SummaryOut(
        summary=row.summary if row else None,
        from_sequence=row.from_sequence if row else None,
        to_sequence=row.to_sequence if row else None,
        model_id=row.model_id if row else None,
        built_at=row.built_at.value if row else None,
        token_count=row.token_count if row else 0,
        running=conversation.summary_started_at is not None,
        last_error=conversation.summary_error,
    )


@router.get("/conversations/{conversation_id}/handoff-preview")
async def handoff_preview(
    conversation_id: uuid.UUID,
    model_id: uuid.UUID,
    session: DbSession,
    user_id: CurrentUserId,
    gateway: GatewayDep,
) -> dict[str, Any]:
    """Exactly what would be sent to `model_id`: every section, its tokens, the budget, the
    total and what is dropped. No LLM call, no keys."""
    return await service.preview_handoff(session, gateway, user_id, conversation_id, model_id)


@router.get("/projects/{project_id}/memory/pinned")
async def pinned_preview(
    project_id: uuid.UUID,
    model_id: uuid.UUID,
    session: DbSession,
    user_id: CurrentUserId,
    gateway: GatewayDep,
) -> dict[str, Any]:
    """The project memory that would be pinned for `model_id` now: the exact text, its tokens,
    and the ids left out with the reason (kind_cap or budget). No LLM call.

    Served here, not by the projects module, because it needs the model's token counter.
    """
    return await service.preview_pinned(session, gateway, user_id, project_id, model_id)


@router.post("/conversations/{conversation_id}/switch-model")
async def switch_model(
    conversation_id: uuid.UUID,
    body: SwitchModelIn,
    session: DbSession,
    user_id: CurrentUserId,
    gateway: GatewayDep,
) -> SwitchOut:
    result = await service.switch_model(
        session, gateway, user_id, conversation_id, body.model_id, HandoffReason(body.reason)
    )
    await session.refresh(result.conversation)
    return SwitchOut(
        conversation=_out(result.conversation),
        handoff=HandoffOut.model_validate(result.handoff),
        preview=result.preview,
    )


@router.get("/conversations/{conversation_id}/handoffs")
async def list_handoffs(
    conversation_id: uuid.UUID, session: DbSession, user_id: CurrentUserId
) -> list[HandoffOut]:
    await service.get_conversation(session, user_id, conversation_id)
    rows = await ContextHandoffRepository(session, user_id).list(
        conversation_id=conversation_id, limit=500
    )
    return [HandoffOut.model_validate(h) for h in rows]
