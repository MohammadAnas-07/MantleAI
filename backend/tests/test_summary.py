"""Rolling summary tests with a deterministic fake summarizer. No keys, no network."""

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.modules.conversations.repository import (
    ConversationRepository,
    ConversationSummaryRepository,
)
from app.modules.conversations.summary import run_rolling_summary
from app.modules.llm.gateway import Gateway
from app.modules.llm.repository import UsageRecordRepository, UserModelSettingsRepository
from app.modules.llm.service import ProviderUnavailable
from tests.conversation_helpers import (
    World,
    add_messages,
    make_world,
    session_factory,
    summarizer_provider,
    turns,
)

pytestmark = pytest.mark.db


@pytest.fixture(autouse=True)
def small_thresholds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "summary_trigger_tokens", 500)
    monkeypatch.setattr(settings, "context_keep_recent_turns", 1)


@pytest.fixture
async def world(session: AsyncSession) -> World:
    return await make_world(session)


async def run(session: AsyncSession, gateway: Gateway, world: World) -> str:
    return await run_rolling_summary(
        session_factory(session), gateway, world.user_id, world.conversation_id
    )


async def test_below_threshold_makes_no_call(session: AsyncSession, world: World) -> None:
    fake = summarizer_provider(world.litellm("small"))
    await add_messages(session, world, turns(1, 2))  # 4 x 100 tokens, 2 of them kept verbatim
    assert await run(session, Gateway(fake), world) == "below_threshold"
    assert fake.calls == []


async def test_triggers_at_threshold_and_uses_the_utility_model(
    session: AsyncSession, world: World
) -> None:
    fake = summarizer_provider(world.litellm("small"), world.litellm("medium"))
    await UserModelSettingsRepository(session, world.user_id).add(
        utility_model_id=world.id("medium")
    )
    # 5 turns = 10 messages. The latest user message and one turn before it (#7-#10) stay
    # verbatim, so #1-#6 = 600 tokens >= 500.
    await add_messages(session, world, turns(1, 5))

    assert await run(session, Gateway(fake), world) == "done"

    assert [c.model for c in fake.calls] == [world.litellm("medium")]  # utility, not active
    summary = await ConversationSummaryRepository(session, world.user_id).latest(
        world.conversation_id
    )
    assert summary is not None
    assert (summary.from_sequence, summary.to_sequence) == (1, 6)
    assert summary.summary == "covered 1,2,3,4,5,6"
    assert summary.model_id == world.id("medium")
    [usage] = await UsageRecordRepository(session, world.user_id).list()
    assert (usage.purpose, usage.trigger) == ("rolling_summary", "background")
    assert usage.conversation_id == world.conversation_id


async def test_summary_is_incremental(session: AsyncSession, world: World) -> None:
    fake = summarizer_provider(world.litellm("small"))
    gateway = Gateway(fake)
    await add_messages(session, world, turns(1, 5))
    assert await run(session, gateway, world) == "done"  # covers 1-6

    await add_messages(session, world, turns(6, 3))  # #11-#16; #13-#16 stay verbatim
    assert await run(session, gateway, world) == "done"

    second_prompt = fake.calls[1].messages[-1]["content"]
    assert "covered 1,2,3,4,5,6" in second_prompt  # the previous summary is the base
    assert "[#7 " in second_prompt and "[#12 " in second_prompt
    assert "[#6 " not in second_prompt  # already covered: not sent again
    assert "[#13 " not in second_prompt  # kept verbatim

    latest = await ConversationSummaryRepository(session, world.user_id).latest(
        world.conversation_id
    )
    assert latest is not None
    assert (latest.from_sequence, latest.to_sequence) == (1, 12)
    assert latest.summary == "covered 1,2,3,4,5,6 | covered 7,8,9,10,11,12"


async def test_only_one_job_at_a_time(session: AsyncSession, world: World) -> None:
    fake = summarizer_provider(world.litellm("small"))
    await add_messages(session, world, turns(1, 5))
    conversations = ConversationRepository(session, world.user_id)

    assert await conversations.claim_lock(world.conversation_id, "summary")  # a job is running
    assert not await conversations.claim_lock(world.conversation_id, "summary")
    assert await run(session, Gateway(fake), world) == "locked"
    assert fake.calls == []

    # A stale lock (crashed job) is taken over.
    await session.execute(
        text("UPDATE conversations SET summary_started_at = now() - interval '1 day' "
             "WHERE id = :id"),
        {"id": world.conversation_id},
    )  # fmt: skip
    assert await run(session, Gateway(fake), world) == "done"
    conversation = await conversations.get(world.conversation_id)
    assert conversation is not None and conversation.summary_started_at is None  # released


async def test_switched_off_means_no_background_call(session: AsyncSession, world: World) -> None:
    fake = summarizer_provider(world.litellm("small"))
    await UserModelSettingsRepository(session, world.user_id).add(background_summary_enabled=False)
    await add_messages(session, world, turns(1, 6))
    assert await run(session, Gateway(fake), world) == "off"
    assert fake.calls == []


async def test_failure_is_stored_and_lock_released(session: AsyncSession, world: World) -> None:
    fake = summarizer_provider()
    fake.fail(world.litellm("small"), ProviderUnavailable("down"))
    await add_messages(session, world, turns(1, 5))

    assert await run(session, Gateway(fake), world) == "failed"

    conversation = await ConversationRepository(session, world.user_id).get(world.conversation_id)
    assert conversation is not None
    assert conversation.summary_error == "provider_unavailable"
    assert conversation.summary_started_at is None
    [usage] = await UsageRecordRepository(session, world.user_id).list()
    assert usage.status == "error"
