"""Rolling conversation summary (D3, D10).

Incremental: the new summary = the previous summary + the messages after its `to_sequence`. The
last few turns (CONTEXT_KEEP_RECENT_TURNS) are never summarized; they are always sent verbatim.

Two ways it runs:
- Background, after an assistant reply, when the summarizable messages not yet covered pass
  SUMMARY_TRIGGER_TOKENS. Uses the utility model (default: the active model). Logged as
  purpose `rolling_summary`, trigger `background`. Skipped when background summaries are off.
- At switch time, when background summaries are off. Uses the NEW model (never the old one).
  Logged as purpose `switch_summary`, trigger `user` (the user asked for the switch).

Only one summary job per conversation runs at a time (`conversations.summary_started_at`).
A failed job stores its error code on the conversation (rule 55) and never breaks chat.
"""

import logging
import uuid
from collections.abc import Callable, Sequence
from contextlib import AbstractAsyncContextManager

import anyio
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.modules.conversations.context_builder import (
    HistoryMessage,
    required_start,
    to_chat_messages,
)
from app.modules.conversations.models import (
    Conversation,
    ConversationSummary,
    Message,
    MessageStatus,
    SummaryBuiltAt,
)
from app.modules.conversations.prompts import SUMMARY_PROMPT, load_prompt
from app.modules.conversations.repository import (
    ConversationRepository,
    ConversationSummaryRepository,
    MessageRepository,
)
from app.modules.llm.service import (
    Gateway,
    LLMError,
    UsageLinks,
    UsagePurpose,
    UsageTrigger,
    count_tokens,
    get_chat_model,
    get_model_settings,
)

logger = logging.getLogger(__name__)

SessionFactory = Callable[[], AbstractAsyncContextManager[AsyncSession]]

# Messages that hold finished text. Streaming placeholders and failed empty replies are skipped.
_SUMMARIZABLE = {MessageStatus.COMPLETE, MessageStatus.CANCELLED}


def to_history(message: Message) -> HistoryMessage:
    return HistoryMessage(message.sequence, message.role.value, list(message.content))


def usable(messages: Sequence[Message]) -> list[Message]:
    return [m for m in messages if m.status in _SUMMARIZABLE and m.content]


def summarizable(messages: Sequence[Message], keep_recent_turns: int) -> list[Message]:
    """Uncovered messages that may be summarized: all but the last turns kept verbatim."""
    items = usable(messages)
    cut = required_start([to_history(m) for m in items], keep_recent_turns)
    return items[:cut]


def format_for_summary(messages: Sequence[Message]) -> str:
    lines = []
    for m in messages:
        chat = to_chat_messages(to_history(m), supports_tools=False)[0]
        lines.append(f"[#{m.sequence} {m.role.value}] {chat['content']}")
    return "\n\n".join(lines)


async def pending(
    session: AsyncSession, user_id: uuid.UUID, conversation_id: uuid.UUID
) -> tuple[ConversationSummary | None, list[Message]]:
    """The current summary and the summarizable messages it doesn't cover yet."""
    previous = await ConversationSummaryRepository(session, user_id).latest(conversation_id)
    after = previous.to_sequence if previous else 0
    uncovered = await MessageRepository(session, user_id).in_order(
        conversation_id, after_sequence=after
    )
    return previous, summarizable(uncovered, settings.context_keep_recent_turns)


def tokens_of(messages: Sequence[Message]) -> int:
    return sum(m.token_count for m in messages)


async def build_summary(
    session: AsyncSession,
    gateway: Gateway,
    user_id: uuid.UUID,
    conversation: Conversation,
    model_id: uuid.UUID,
    *,
    purpose: UsagePurpose,
    trigger: UsageTrigger,
    built_at: SummaryBuiltAt,
) -> ConversationSummary | None:
    """Write a new summary row covering everything summarizable. None if nothing new."""
    previous, new_messages = await pending(session, user_id, conversation.id)
    if not new_messages:
        return None
    prompt = load_prompt(SUMMARY_PROMPT).format(
        previous_summary=previous.summary if previous else "(none yet)",
        new_messages=format_for_summary(new_messages),
        max_words=int(settings.summary_max_output_tokens * 0.6),
    )
    done = await gateway.complete(
        session,
        user_id,
        model_id,
        [{"role": "user", "content": prompt}],
        purpose=purpose,
        trigger=trigger,
        max_tokens=settings.summary_max_output_tokens,
        links=UsageLinks(project_id=conversation.project_id, conversation_id=conversation.id),
    )
    model = await get_chat_model(session, model_id)
    last = new_messages[-1]
    return await ConversationSummaryRepository(session, user_id).add(
        conversation_id=conversation.id,
        from_sequence=previous.from_sequence if previous else new_messages[0].sequence,
        to_sequence=last.sequence,
        summary=done.text,
        up_to_message_id=last.id,
        model_id=model_id,
        built_at=built_at,
        token_count=count_tokens(gateway, model, [{"role": "system", "content": done.text}]),
    )


async def run_rolling_summary(
    session_factory: SessionFactory,
    gateway: Gateway,
    user_id: uuid.UUID,
    conversation_id: uuid.UUID,
) -> str:
    """The background job. Returns what happened, for tests and logs:
    `done`, `off`, `below_threshold`, `locked`, `failed` or `missing`."""
    async with session_factory() as session:
        conversations = ConversationRepository(session, user_id)
        conversation = await conversations.get(conversation_id)
        if conversation is None:
            return "missing"
        model_settings = await get_model_settings(session, user_id)
        if not model_settings.background_summary_enabled:
            return "off"
        _, new_messages = await pending(session, user_id, conversation_id)
        if tokens_of(new_messages) < settings.summary_trigger_tokens:
            return "below_threshold"
        if not await conversations.claim_lock(conversation_id, "summary"):
            await session.commit()
            return "locked"
        await session.commit()

        outcome = "done"
        model_id = model_settings.utility_model_id or conversation.current_model_id
        try:
            await build_summary(
                session,
                gateway,
                user_id,
                conversation,
                model_id,
                purpose=UsagePurpose.ROLLING_SUMMARY,
                trigger=UsageTrigger.BACKGROUND,
                built_at=SummaryBuiltAt.BACKGROUND,
            )
            conversation.summary_error = None
        except LLMError as exc:
            outcome, conversation.summary_error = "failed", exc.code
        except Exception as exc:
            # Never break chat (rule 55). Log the type only: database errors can carry the
            # message text in their parameters (rule 53).
            logger.error(
                "rolling summary crashed conversation=%s type=%s",
                conversation_id,
                type(exc).__name__,
            )
            await session.rollback()
            outcome, conversation.summary_error = "failed", "internal_error"
        finally:
            with anyio.CancelScope(shield=True):
                await conversations.release_lock(conversation_id, "summary")
                await session.commit()
        logger.info("rolling summary conversation=%s outcome=%s", conversation_id, outcome)
        return outcome
