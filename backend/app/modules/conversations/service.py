"""Public interface of the conversations module: conversations, streamed replies, handoff preview
and model switching.

The conversation in our database is the source of truth, never a provider's session. Mantle
never switches models by itself; on ContextTooLong, RateLimited or QuotaExhausted it returns
`suggested_models` and the user decides. A switch only changes `current_model_id` and never
calls the old model.
"""

import logging
import uuid
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import anyio
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import AppError, NotFound
from app.modules.conversations.context_builder import (
    BudgetSettings,
    BuiltContext,
    ContextBuilder,
    ContextInputs,
    HistoryMessage,
    SummaryInput,
    compute_budget,
)
from app.modules.conversations.models import (
    ContextHandoff,
    ContextSourceType,
    Conversation,
    HandoffReason,
    Message,
    MessageRole,
    MessageStatus,
    SummaryBuiltAt,
)
from app.modules.conversations.repository import (
    ContextHandoffRepository,
    ConversationRepository,
    ConversationSummaryRepository,
    MessageContextRepository,
    MessageRepository,
)
from app.modules.conversations.summary import (
    SessionFactory,
    build_summary,
    pending,
    to_history,
    tokens_of,
    usable,
)
from app.modules.llm.service import (
    ChatDelta,
    ChatDone,
    ContextTooLong,
    Gateway,
    LLMError,
    ModelInfo,
    NoCredential,
    UsageLinks,
    UsagePurpose,
    UsageTrigger,
    count_tokens,
    get_chat_model,
    get_model_settings,
    providers_with_keys,
    suggest_models,
)
from app.modules.projects.service import (
    DroppedPin,
    PinnedSelection,
    get_project,
    pinned_block,
    pinned_selection,
)
from app.modules.rag.service import (
    RetrievedBlock,
    blocks_for_chunks,
    profile_facts,
    retrieve_for_context,
)

logger = logging.getLogger(__name__)

TITLE_LENGTH = 60
_SUGGEST_FOR = {"context_too_long", "rate_limited", "quota_exhausted"}


class GenerationInProgress(AppError):
    status_code = 409
    code = "generation_in_progress"


# ---- conversations ---------------------------------------------------------------------------


async def get_conversation(
    session: AsyncSession, user_id: uuid.UUID, conversation_id: uuid.UUID
) -> Conversation:
    conversation = await ConversationRepository(session, user_id).get(conversation_id)
    if conversation is None:
        raise NotFound("Conversation not found.")
    return conversation


async def create_conversation(
    session: AsyncSession,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
    model_id: uuid.UUID,
    title: str = "",
) -> Conversation:
    await get_project(session, user_id, project_id)  # 404 if not this user's project
    await get_chat_model(session, model_id)
    return await ConversationRepository(session, user_id).add(
        project_id=project_id, current_model_id=model_id, title=title[:300]
    )


async def list_conversations(
    session: AsyncSession, user_id: uuid.UUID, project_id: uuid.UUID
) -> Sequence[Conversation]:
    await get_project(session, user_id, project_id)
    return await ConversationRepository(session, user_id).list(project_id=project_id, limit=500)


async def list_messages(
    session: AsyncSession,
    user_id: uuid.UUID,
    conversation_id: uuid.UUID,
    after_sequence: int = 0,
    limit: int = 100,
) -> Sequence[Message]:
    await get_conversation(session, user_id, conversation_id)
    return await MessageRepository(session, user_id).in_order(
        conversation_id, after_sequence=after_sequence, limit=limit
    )


# ---- context ---------------------------------------------------------------------------------


async def _require_key(session: AsyncSession, user_id: uuid.UUID, model: ModelInfo) -> None:
    if model.provider not in await providers_with_keys(session, user_id):
        raise NoCredential(
            f"Add an API key for {model.provider} to use {model.display_name}.",
            details={"provider": model.provider},
        )


def pinned_token_budget(model: ModelInfo) -> int:
    """The share of the model's context budget that pinned memory may use."""
    budget, _, _ = compute_budget(model, BudgetSettings.from_settings())
    return max(int(budget * settings.pinned_max_share), 0)


async def select_pinned_for(
    session: AsyncSession,
    gateway: Gateway,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
    model: ModelInfo,
) -> PinnedSelection:
    """Pinned memory for `model`, counted with that model's token counter."""
    return await pinned_selection(
        session, user_id, project_id,
        max_tokens=pinned_token_budget(model),
        count=lambda text: count_tokens(gateway, model, [{"role": "system", "content": text}]),
    )  # fmt: skip


async def last_retrieved(
    session: AsyncSession, user_id: uuid.UUID, conversation: Conversation
) -> list[RetrievedBlock]:
    """The code sent with the newest reply, read back from its message_contexts rows. Used by
    the handoff preview and the switch, which make no model call (so no query embedding)."""
    if not conversation.code_context_enabled:
        return []
    refs = await MessageContextRepository(session, user_id).latest_chunks(conversation.id)
    return await blocks_for_chunks(session, user_id, conversation.project_id, refs)


async def load_inputs(
    session: AsyncSession,
    gateway: Gateway,
    user_id: uuid.UUID,
    conversation: Conversation,
    model: ModelInfo,
    new_user_text: str | None = None,
    retrieved: list[RetrievedBlock] | None = None,
) -> ContextInputs:
    """Everything the context builder needs, read from the database. Optionally adds the user
    message that is about to be sent (not saved yet). Without `retrieved`, the code of the
    newest reply is used."""
    if retrieved is None:
        retrieved = await last_retrieved(session, user_id, conversation)
    project = await get_project(session, user_id, conversation.project_id)
    pinned = await select_pinned_for(session, gateway, user_id, conversation.project_id, model)
    # The same stored facts for every model, so a switch carries the profile unchanged.
    profile = await profile_facts(session, user_id, conversation.project_id)
    summary_row = await ConversationSummaryRepository(session, user_id).latest(conversation.id)
    after = summary_row.to_sequence if summary_row else 0
    messages = await MessageRepository(session, user_id).in_order(
        conversation.id, after_sequence=after
    )
    history = [to_history(m) for m in usable(messages)]
    if new_user_text is not None:
        next_seq = (messages[-1].sequence if messages else after) + 1
        history.append(HistoryMessage(next_seq, "user", [{"type": "text", "text": new_user_text}]))
    summary = (
        SummaryInput(summary_row.summary, summary_row.from_sequence, summary_row.to_sequence)
        if summary_row
        else None
    )
    return ContextInputs(
        project=project,
        pinned=pinned.items,
        summary=summary,
        history=history,
        retrieved=retrieved,
        pinned_dropped=pinned.dropped,
        profile=profile,
    )


async def build_context(
    session: AsyncSession,
    gateway: Gateway,
    user_id: uuid.UUID,
    conversation: Conversation,
    model: ModelInfo,
    new_user_text: str | None = None,
    retrieved: list[RetrievedBlock] | None = None,
) -> BuiltContext:
    """Build the request for `model`. No LLM call. ContextTooLong carries suggested_models."""
    inputs = await load_inputs(
        session, gateway, user_id, conversation, model, new_user_text, retrieved
    )
    builder = ContextBuilder(lambda messages: count_tokens(gateway, model, messages))
    try:
        return builder.build(model, inputs)
    except ContextTooLong as exc:
        exc.details["suggested_models"] = await suggest_models(
            session, user_id, model, "context_too_long"
        )
        raise


def context_report(built: BuiltContext) -> dict[str, Any]:
    """What would be sent, section by section. Never contains keys (none are in the context)."""
    return {
        "model_id": str(built.model.id),
        "model": built.model.display_name,
        "context_window": built.context_window,
        "reserved_output_tokens": built.reserved_output_tokens,
        "safety_margin_tokens": built.safety_margin_tokens,
        "budget": built.budget,
        "total_tokens": built.total_tokens,
        "sections": [
            {
                "name": s.name,
                "included": s.included,
                "tokens": s.tokens,
                "items_total": s.items_total,
                "items_included": s.items_included,
                "content": s.content,
            }
            for s in built.sections
        ],
        "dropped": built.dropped,
        "pinned": {
            "tokens": built.pinned_tokens,
            "max_tokens": pinned_token_budget(built.model),
            "included": built.pinned_included,
            "dropped": dropped_report(built.pinned_dropped),
        },
        "profile": {
            "tokens": built.profile_tokens,
            "max_tokens": built.profile_max_tokens,
            "fields": built.profile_fields,
            "dropped": [{"field": f, "reason": r} for f, r in built.profile_dropped],
        },
        "retrieved": {
            "tokens": built.retrieved_tokens,
            "max_tokens": built.retrieved_max_tokens,
            "used": [block_report(b) for b in built.retrieved_used],
            "dropped": [
                block_report(d.block) | {"reason": d.reason} for d in built.retrieved_dropped
            ],
        },
    }


def block_report(block: RetrievedBlock) -> dict[str, Any]:
    """A retrieved block without its text: where it is from and how it ranked."""
    return {
        "path": block.path,
        "start_line": block.start_line,
        "end_line": block.end_line,
        "symbol": block.symbol,
        "score": block.score,
        "vector_rank": block.vector_rank,
        "text_rank": block.text_rank,
        "chunk_ids": [str(c) for c in block.chunk_ids],
    }


def dropped_report(dropped: list[DroppedPin]) -> list[dict[str, str]]:
    return [{"id": str(d.id), "kind": d.kind, "reason": d.reason} for d in dropped]


async def preview_pinned(
    session: AsyncSession,
    gateway: Gateway,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
    model_id: uuid.UUID,
) -> dict[str, Any]:
    """What would be pinned for `model_id` right now, and what is left out and why. No LLM call."""
    model = await get_chat_model(session, model_id)
    selection = await select_pinned_for(session, gateway, user_id, project_id, model)
    return {
        "model_id": str(model.id),
        "max_tokens": pinned_token_budget(model),
        "tokens": selection.tokens,
        "text": pinned_block(selection.items),
        "items": [
            {"id": str(i.id), "kind": i.kind, "status": i.status, "line": i.line}
            for i in selection.items
        ],  # fmt: skip
        "dropped": dropped_report(selection.dropped),
    }


# ---- replies (SSE) ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SseEvent:
    event: str  # message_start | warning | delta | message_end | error
    data: dict[str, Any]


@dataclass(frozen=True)
class PreparedReply:
    conversation_id: uuid.UUID
    project_id: uuid.UUID
    model: ModelInfo
    built: BuiltContext
    user_message_id: uuid.UUID
    assistant_message_id: uuid.UUID
    # Problems that did not stop the reply, sent as SSE "warning" events.
    warnings: tuple[dict[str, Any], ...] = ()


async def retrieve_code(
    session: AsyncSession,
    gateway: Gateway,
    user_id: uuid.UUID,
    conversation: Conversation,
    query: str,
) -> tuple[list[RetrievedBlock], dict[str, Any] | None]:
    """Project code for this message, and a warning when it could not be used.

    Retrieval must never fail the message: a provider error (rate limit, bad key, provider
    down) or any other failure means no retrieved code plus a warning. The query embedding is
    logged with purpose "embedding" (its usage row is kept even when it fails).
    """
    if not conversation.code_context_enabled:
        return [], None
    links = UsageLinks(project_id=conversation.project_id, conversation_id=conversation.id)
    llm_error: LLMError | None = None
    try:
        async with session.begin_nested():  # a database error here must not break the reply
            try:
                outcome = await retrieve_for_context(
                    session, gateway, user_id, conversation.project_id, query, links
                )
            except LLMError as exc:
                llm_error = exc  # leave the savepoint normally, so the usage row stays
    except Exception as exc:
        logger.warning(
            "retrieval failed conversation=%s type=%s", conversation.id, type(exc).__name__
        )
        return [], {
            "code": "retrieval_failed",
            "message": "Project code was not used: retrieval failed.",
            "details": {},
        }
    if llm_error is not None:
        logger.warning("retrieval skipped conversation=%s code=%s", conversation.id, llm_error.code)
        return [], {
            "code": "retrieval_failed",
            "message": f"Project code was not used: the embedding call failed ({llm_error.code}).",
            "details": {"error_code": llm_error.code},
        }
    return outcome.blocks, outcome.warning


def _lock_held(since: datetime | None) -> bool:
    if since is None:
        return False
    age = datetime.now(UTC) - since
    return age < timedelta(seconds=settings.conversation_lock_timeout_seconds)


async def prepare_reply(
    session: AsyncSession,
    gateway: Gateway,
    user_id: uuid.UUID,
    conversation_id: uuid.UUID,
    text: str,
) -> PreparedReply:
    """Check everything that can fail before streaming, then save the user message and an
    empty assistant message. Errors here are normal HTTP errors (404, 409, 413, 422)."""
    conversation = await get_conversation(session, user_id, conversation_id)
    model = await get_chat_model(session, conversation.current_model_id)
    await _require_key(session, user_id, model)
    if _lock_held(conversation.generating_since):
        # A cheap early check, so a refused message costs no query embedding. The atomic
        # claim below still decides.
        raise GenerationInProgress("A reply is already being generated for this conversation.")
    retrieved, warning = await retrieve_code(session, gateway, user_id, conversation, text)
    built = await build_context(
        session, gateway, user_id, conversation, model, new_user_text=text, retrieved=retrieved
    )

    conversations = ConversationRepository(session, user_id)
    if not await conversations.claim_lock(conversation_id, "generating"):
        raise GenerationInProgress("A reply is already being generated for this conversation.")

    messages = MessageRepository(session, user_id)
    sequence = await messages.next_sequence(conversation_id)
    user_message = await messages.add(
        conversation_id=conversation_id,
        sequence=sequence,
        role=MessageRole.USER,
        content=[{"type": "text", "text": text}],
        status=MessageStatus.COMPLETE,
        token_count=count_tokens(gateway, model, [{"role": "user", "content": text}]),
    )
    assistant = await messages.add(
        conversation_id=conversation_id,
        sequence=sequence + 1,
        role=MessageRole.ASSISTANT,
        content=[],
        model_id=model.id,
        status=MessageStatus.STREAMING,
    )
    # What was sent: ids and line ranges only, never the text.
    contexts = MessageContextRepository(session, user_id)
    for rank, block in enumerate(built.retrieved_used, start=1):
        for chunk_id in block.chunk_ids:
            await contexts.add(
                message_id=assistant.id,
                source_type=ContextSourceType.CHUNK,
                source_id=chunk_id,
                score=block.score,
                rank=rank,
                start_line=block.start_line,
                end_line=block.end_line,
            )
    if not conversation.title:
        conversation.title = text.strip()[:TITLE_LENGTH]  # no LLM call for titles
    await session.commit()
    return PreparedReply(
        conversation_id, conversation.project_id, model, built, user_message.id, assistant.id,
        warnings=(warning,) if warning else (),
    )  # fmt: skip


async def _finish(
    session: AsyncSession,
    user_id: uuid.UUID,
    prepared: PreparedReply,
    *,
    text: str,
    status: MessageStatus,
    error_code: str | None,
    done: ChatDone | None,
    gateway: Gateway,
) -> None:
    """Save the assistant message and release the generation lock. Shielded from cancellation."""
    with anyio.CancelScope(shield=True):
        if not session.is_active:
            # A database error earlier in this stream left the transaction unusable.
            await session.rollback()
        messages = MessageRepository(session, user_id)
        values: dict[str, Any] = {
            "content": [{"type": "text", "text": text}] if text else [],
            "status": status,
            "error_code": error_code,
            "token_count": count_tokens(
                gateway, prepared.model, [{"role": "assistant", "content": text}]
            )
            if text
            else 0,
        }
        if done is not None:
            values |= {"input_tokens": done.input_tokens, "output_tokens": done.output_tokens}
        await messages.update(prepared.assistant_message_id, **values)
        await ConversationRepository(session, user_id).release_lock(
            prepared.conversation_id, "generating"
        )
        await session.commit()


async def stream_reply(
    session_factory: SessionFactory,
    gateway: Gateway,
    user_id: uuid.UUID,
    prepared: PreparedReply,
) -> AsyncIterator[SseEvent]:
    """Stream the reply as SSE events: message_start, delta..., then message_end or error.

    The assistant message is saved when the stream ends. If the client disconnects, the
    upstream call is cancelled and the partial text is saved with status `cancelled`.
    """
    async with session_factory() as session:
        yield SseEvent(
            "message_start",
            {
                "message_id": str(prepared.assistant_message_id),
                "user_message_id": str(prepared.user_message_id),
                "conversation_id": str(prepared.conversation_id),
                "model_id": str(prepared.model.id),
                "sources": [block_report(b) for b in prepared.built.retrieved_used],
            },
        )
        for warning in prepared.warnings:
            yield SseEvent("warning", {"message_id": str(prepared.assistant_message_id)} | warning)
        parts: list[str] = []
        done: ChatDone | None = None
        stream = gateway.stream_chat(
            session,
            user_id,
            prepared.model.id,
            prepared.built.messages,
            purpose=UsagePurpose.CHAT,
            trigger=UsageTrigger.USER,
            max_tokens=prepared.built.reserved_output_tokens,
            links=UsageLinks(
                project_id=prepared.project_id,
                conversation_id=prepared.conversation_id,
                message_id=prepared.assistant_message_id,
            ),
        )
        try:
            async for event in stream:
                if isinstance(event, ChatDelta):
                    parts.append(event.text)
                    yield SseEvent("delta", {"text": event.text})
                else:
                    done = event
        except LLMError as exc:
            await _finish(session, user_id, prepared, text="".join(parts),
                          status=MessageStatus.ERROR, error_code=exc.code, done=None,
                          gateway=gateway)  # fmt: skip
            details = dict(exc.details)
            if exc.code in _SUGGEST_FOR:
                details["suggested_models"] = await suggest_models(
                    session, user_id, prepared.model, exc.code
                )
            yield SseEvent(
                "error",
                {
                    "message_id": str(prepared.assistant_message_id),
                    "code": exc.code,
                    "message": exc.message,
                    "details": details,
                },
            )
            return
        except Exception as exc:
            # A bug or a database error, not the provider and not a disconnect: say so instead
            # of calling it a cancel, keep what arrived, and log the type only (rule 53).
            logger.error("reply failed conversation=%s type=%s", prepared.conversation_id,
                         type(exc).__name__)  # fmt: skip
            with anyio.CancelScope(shield=True):
                await stream.aclose()
            await _finish(session, user_id, prepared, text="".join(parts),
                          status=MessageStatus.ERROR, error_code="internal_error", done=None,
                          gateway=gateway)  # fmt: skip
            yield SseEvent(
                "error",
                {
                    "message_id": str(prepared.assistant_message_id),
                    "code": "internal_error",
                    "message": "The reply stopped on an internal error. The text so far is saved.",
                    "details": {},
                },
            )
            return
        except BaseException:
            # Client disconnected (cancellation) or the server is stopping: stop the upstream
            # call, keep what arrived.
            with anyio.CancelScope(shield=True):
                await stream.aclose()
            await _finish(session, user_id, prepared, text="".join(parts),
                          status=MessageStatus.CANCELLED, error_code=None, done=None,
                          gateway=gateway)  # fmt: skip
            logger.info("reply cancelled conversation=%s", prepared.conversation_id)
            raise

        assert done is not None
        await _finish(session, user_id, prepared, text=done.text, status=MessageStatus.COMPLETE,
                      error_code=None, done=done, gateway=gateway)  # fmt: skip
        yield SseEvent(
            "message_end",
            {
                "message_id": str(prepared.assistant_message_id),
                "usage": {
                    "input_tokens": done.input_tokens,
                    "output_tokens": done.output_tokens,
                    "cost_usd": str(done.cost_usd) if done.cost_usd is not None else None,
                    "latency_ms": done.latency_ms,
                },
            },
        )


# ---- handoff preview and switching -----------------------------------------------------------


async def _will_build_summary(
    session: AsyncSession, user_id: uuid.UUID, conversation: Conversation
) -> tuple[bool, int]:
    """Whether a switch now would write the summary (background summaries off + enough
    unsummarized history), and how many tokens it would read."""
    model_settings = await get_model_settings(session, user_id)
    if model_settings.background_summary_enabled:
        return False, 0
    _, new_messages = await pending(session, user_id, conversation.id)
    tokens = tokens_of(new_messages)
    return tokens >= settings.summary_trigger_tokens, tokens


async def preview_handoff(
    session: AsyncSession,
    gateway: Gateway,
    user_id: uuid.UUID,
    conversation_id: uuid.UUID,
    model_id: uuid.UUID,
) -> dict[str, Any]:
    """Exactly what would be sent to `model_id` now. No LLM call."""
    conversation = await get_conversation(session, user_id, conversation_id)
    model = await get_chat_model(session, model_id)
    built = await build_context(session, gateway, user_id, conversation, model)
    will_build, summary_input_tokens = await _will_build_summary(session, user_id, conversation)
    report = context_report(built)
    report["has_key"] = model.provider in await providers_with_keys(session, user_id)
    report["will_build_summary"] = will_build
    report["summary_input_tokens"] = summary_input_tokens if will_build else 0
    return report


def handoff_note(
    built: BuiltContext, from_model: ModelInfo, summary_built_now: bool
) -> dict[str, Any]:
    """The note shown to the user after a switch. Built WITHOUT an LLM; never sent to a model."""
    summary = (
        {"from_sequence": built.summary_range[0], "to_sequence": built.summary_range[1],
         "tokens": built.summary_tokens}
        if built.summary_range
        else None
    )  # fmt: skip
    lines = [f"Switched from {from_model.display_name} to {built.model.display_name}."]
    if built.messages_verbatim:
        lines.append(
            f"{built.messages_verbatim} messages carried verbatim, from "
            f"#{built.first_verbatim_sequence}."
        )
    else:
        lines.append("No messages carried verbatim.")
    if summary:
        made = " (written now by the new model)" if summary_built_now else ""
        lines.append(
            f"Summary covers messages {summary['from_sequence']}-{summary['to_sequence']}, "
            f"{summary['tokens']} tokens{made}."
        )
    left_out = len(built.pinned_dropped)
    lines.append(
        f"{built.pinned_included} pinned items ({built.pinned_tokens} tokens)"
        + (f", {left_out} left out." if left_out else ".")
    )
    if built.retrieved_used or built.retrieved_dropped:
        lines.append(
            f"{len(built.retrieved_used)} code sources ({built.retrieved_tokens} tokens)"
            + (f", {len(built.retrieved_dropped)} left out." if built.retrieved_dropped else ".")
        )
    lines.append("Dropped: " + (", ".join(built.dropped) if built.dropped else "nothing") + ".")
    return {
        "text": " ".join(lines),
        "from_model": from_model.display_name,
        "to_model": built.model.display_name,
        "messages_verbatim": built.messages_verbatim,
        "first_verbatim_sequence": built.first_verbatim_sequence,
        "summary": summary,
        "summary_built_at_switch": summary_built_now,
        "pinned_items": built.pinned_included,
        "pinned_tokens": built.pinned_tokens,
        "pinned_dropped": dropped_report(built.pinned_dropped),
        "retrieved": [block_report(b) for b in built.retrieved_used],
        "retrieved_dropped": [
            block_report(d.block) | {"reason": d.reason} for d in built.retrieved_dropped
        ],
        "dropped": built.dropped,
        "budget": built.budget,
        "total_tokens": built.total_tokens,
    }


@dataclass(frozen=True)
class SwitchResult:
    conversation: Conversation
    handoff: ContextHandoff
    preview: dict[str, Any]


async def switch_model(
    session: AsyncSession,
    gateway: Gateway,
    user_id: uuid.UUID,
    conversation_id: uuid.UUID,
    model_id: uuid.UUID,
    reason: HandoffReason = HandoffReason.USER_CHOICE,
) -> SwitchResult:
    """Point the conversation at another model. NEVER calls the old model.

    When background summaries are off and enough history is unsummarized, the summary is
    written now by the NEW model (purpose switch_summary, trigger user).
    """
    conversation = await get_conversation(session, user_id, conversation_id)
    new_model = await get_chat_model(session, model_id)
    if new_model.id == conversation.current_model_id:
        raise AppError("The conversation already uses this model.", code="same_model",
                       status_code=422)  # fmt: skip
    await _require_key(session, user_id, new_model)
    old_model = await get_chat_model(session, conversation.current_model_id)

    conversations = ConversationRepository(session, user_id)
    if not await conversations.claim_lock(conversation_id, "generating"):
        raise GenerationInProgress("Wait for the current reply before switching models.")
    await session.commit()

    try:
        # Size of the context on the old model, for the record. Counting only, no call.
        try:
            tokens_before = (await build_context(session, gateway, user_id, conversation,
                                                 old_model)).total_tokens  # fmt: skip
        except ContextTooLong as exc:
            tokens_before = int(exc.details.get("required_tokens", 0))

        will_build, _ = await _will_build_summary(session, user_id, conversation)
        summary_built = False
        if will_build:
            row = await build_summary(
                session, gateway, user_id, conversation, new_model.id,
                purpose=UsagePurpose.SWITCH_SUMMARY, trigger=UsageTrigger.USER,
                built_at=SummaryBuiltAt.SWITCH,
            )  # fmt: skip
            summary_built = row is not None
            await session.commit()  # keep the summary and its usage row even if the build fails

        built = await build_context(session, gateway, user_id, conversation, new_model)
        summary_row = await ConversationSummaryRepository(session, user_id).latest(conversation_id)
        first_raw = None
        if built.first_verbatim_sequence is not None:
            rows = await MessageRepository(session, user_id).list(
                conversation_id=conversation_id, sequence=built.first_verbatim_sequence, limit=1
            )
            first_raw = rows[0].id if rows else None

        handoff = await ContextHandoffRepository(session, user_id).add(
            conversation_id=conversation_id,
            from_model_id=old_model.id,
            to_model_id=new_model.id,
            reason=reason,
            conversation_summary_id=summary_row.id if built.summary_range and summary_row else None,
            first_raw_message_id=first_raw,
            tokens_before=tokens_before,
            tokens_after=built.total_tokens,
            note=handoff_note(built, old_model, summary_built),
        )
        conversation.current_model_id = new_model.id
    finally:
        with anyio.CancelScope(shield=True):
            await conversations.release_lock(conversation_id, "generating")
            await session.commit()
    logger.info("model switched conversation=%s reason=%s", conversation_id, reason.value)
    return SwitchResult(conversation, handoff, context_report(built))
