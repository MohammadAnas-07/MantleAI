"""Gateway tests with FakeProvider: no keys, no network."""

import logging
import uuid
from contextlib import aclosing
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.llm.catalog import seed_default_models
from app.modules.llm.fake import FakeProvider
from app.modules.llm.gateway import ChatDelta, ChatDone, Gateway, UsageLinks
from app.modules.llm.models import ModelConfig, UsagePurpose, UsageStatus, UsageTrigger
from app.modules.llm.repository import (
    ModelConfigRepository,
    ProviderCredentialRepository,
    UsageRecordRepository,
)
from app.modules.llm.service import (
    ModelUnavailable,
    NoCredential,
    QuotaExhausted,
    RateLimited,
)
from tests.graph import make_user

pytestmark = pytest.mark.db

OPENAI_KEY = "sk-test-openai-key-0000aaaa"
SECRET_PROMPT = "my private design notes about project falcon"


@pytest.fixture
def fake() -> FakeProvider:
    return FakeProvider(default_reply="Use PostgreSQL because it has pgvector.")


@pytest.fixture
def gateway(fake: FakeProvider) -> Gateway:
    return Gateway(fake)


@pytest.fixture
async def user_id(session: AsyncSession) -> uuid.UUID:
    await seed_default_models(session)
    return await make_user(session, "Gwen")


async def model(session: AsyncSession, litellm_model: str) -> ModelConfig:
    found = await ModelConfigRepository(session).get_by_litellm_model(litellm_model)
    assert found is not None
    return found


async def add_key(session: AsyncSession, user_id: uuid.UUID, provider: str, key: str) -> None:
    await ProviderCredentialRepository(session, user_id).add_key(provider=provider, api_key=key)


async def collect(gateway: Gateway, session: AsyncSession, user_id: uuid.UUID, model_id: uuid.UUID,
                  **kwargs: object) -> tuple[list[str], ChatDone]:  # fmt: skip
    deltas: list[str] = []
    done: ChatDone | None = None
    stream = gateway.stream_chat(
        session,
        user_id,
        model_id,
        [{"role": "user", "content": SECRET_PROMPT}],
        purpose=UsagePurpose.CHAT,
        trigger=UsageTrigger.USER,
        **kwargs,  # type: ignore[arg-type]
    )
    async with aclosing(stream):
        async for event in stream:
            if isinstance(event, ChatDelta):
                deltas.append(event.text)
            else:
                done = event
    assert done is not None
    return deltas, done


async def test_stream_writes_one_usage_row(
    session: AsyncSession, gateway: Gateway, fake: FakeProvider, user_id: uuid.UUID
) -> None:
    gpt = await model(session, "openai/gpt-5.6")
    await add_key(session, user_id, "openai", OPENAI_KEY)

    deltas, done = await collect(gateway, session, user_id, gpt.id, links=UsageLinks())

    assert "".join(deltas) == "Use PostgreSQL because it has pgvector."
    assert len(deltas) > 1  # streamed in pieces
    assert done.text == "".join(deltas)
    assert [c.model for c in fake.calls] == ["openai/gpt-5.6"]
    assert fake.calls[0].key_hint == OPENAI_KEY[-4:]

    rows = await UsageRecordRepository(session, user_id).list()
    assert len(rows) == 1
    row = rows[0]
    assert (row.purpose, row.trigger, row.status) == ("chat", "user", UsageStatus.SUCCESS)
    assert row.model_id == gpt.id and row.id == done.usage_record_id
    assert row.input_tokens == done.input_tokens > 0
    assert row.output_tokens == done.output_tokens > 0
    expected = (Decimal(row.input_tokens) * 4 + Decimal(row.output_tokens) * 20) / 1_000_000
    assert row.cost_usd == expected


async def test_newest_key_for_the_provider_is_used(
    session: AsyncSession, gateway: Gateway, fake: FakeProvider, user_id: uuid.UUID
) -> None:
    gpt = await model(session, "openai/gpt-5.6")
    await add_key(session, user_id, "openai", "sk-old-key-000000001111")
    # Both keys are added in one test transaction, where now() is the same; age the first one.
    await session.execute(
        text(
            "UPDATE provider_credentials SET created_at = now() - interval '1 day' "
            "WHERE user_id = :u"
        ),
        {"u": user_id},
    )
    await add_key(session, user_id, "openai", "sk-new-key-000000002222")
    await collect(gateway, session, user_id, gpt.id)
    assert fake.calls[0].key_hint == "2222"


async def test_no_key_for_provider(
    session: AsyncSession, gateway: Gateway, fake: FakeProvider, user_id: uuid.UUID
) -> None:
    claude = await model(session, "anthropic/claude-sonnet-5-5")
    await add_key(session, user_id, "openai", OPENAI_KEY)  # a key, but for another provider
    with pytest.raises(NoCredential) as info:
        await collect(gateway, session, user_id, claude.id)
    assert info.value.details == {"provider": "anthropic"}
    assert fake.calls == []


async def test_disabled_or_wrong_kind_model(
    session: AsyncSession, gateway: Gateway, user_id: uuid.UUID
) -> None:
    await add_key(session, user_id, "openai", OPENAI_KEY)
    gpt = await model(session, "openai/gpt-5.6")
    await ModelConfigRepository(session).update(gpt.id, enabled=False)
    with pytest.raises(ModelUnavailable):
        await collect(gateway, session, user_id, gpt.id)
    embed = await model(session, "openai/text-embedding-3-small")
    with pytest.raises(ModelUnavailable):
        await collect(gateway, session, user_id, embed.id)


async def test_provider_error_is_typed_and_recorded(
    session: AsyncSession, gateway: Gateway, fake: FakeProvider, user_id: uuid.UUID
) -> None:
    gpt = await model(session, "openai/gpt-5.6")
    await add_key(session, user_id, "openai", OPENAI_KEY)
    fake.fail("openai/gpt-5.6", RateLimited("slow down"))

    with pytest.raises(RateLimited):
        await collect(gateway, session, user_id, gpt.id)

    [row] = await UsageRecordRepository(session, user_id).list()
    assert row.status == UsageStatus.ERROR
    assert row.error_code == "rate_limited"


async def test_quota_exhausted_is_recorded_with_provider_detail(
    session: AsyncSession, gateway: Gateway, fake: FakeProvider, user_id: uuid.UUID
) -> None:
    gpt = await model(session, "openai/gpt-5.6")
    await add_key(session, user_id, "openai", OPENAI_KEY)
    error = QuotaExhausted("The provider's quota for this model is used up.")
    error.provider_detail = "http=429 status=RESOURCE_EXHAUSTED quota_id=RequestsPerDay"
    fake.fail("openai/gpt-5.6", error)

    with pytest.raises(QuotaExhausted):
        await collect(gateway, session, user_id, gpt.id)

    [row] = await UsageRecordRepository(session, user_id).list()
    assert (row.status, row.error_code) == (UsageStatus.ERROR, "quota_exhausted")
    assert row.error_detail == "http=429 status=RESOURCE_EXHAUSTED quota_id=RequestsPerDay"


async def test_cancelled_stream_is_recorded(
    session: AsyncSession, gateway: Gateway, user_id: uuid.UUID
) -> None:
    gpt = await model(session, "openai/gpt-5.6")
    await add_key(session, user_id, "openai", OPENAI_KEY)
    stream = gateway.stream_chat(
        session,
        user_id,
        gpt.id,
        [{"role": "user", "content": "hi"}],
        purpose=UsagePurpose.CHAT,
        trigger=UsageTrigger.USER,
    )
    async with aclosing(stream):
        first = await anext(stream)
        assert isinstance(first, ChatDelta)
    # Leaving the block closes the stream early, like a client disconnect.

    [row] = await UsageRecordRepository(session, user_id).list()
    assert row.status == UsageStatus.CANCELLED
    assert row.output_tokens > 0  # estimated from the partial text


async def test_complete_and_embed(
    session: AsyncSession, gateway: Gateway, fake: FakeProvider, user_id: uuid.UUID
) -> None:
    await add_key(session, user_id, "openai", OPENAI_KEY)
    gpt = await model(session, "openai/gpt-5.6")
    embed = await model(session, "openai/text-embedding-3-small")

    done = await gateway.complete(
        session,
        user_id,
        gpt.id,
        [{"role": "user", "content": "hi"}],
        purpose=UsagePurpose.ROLLING_SUMMARY,
        trigger=UsageTrigger.BACKGROUND,
    )
    assert done.text == fake.default_reply
    vectors = await gateway.embed(session, user_id, embed.id, ["a", "b"], trigger=UsageTrigger.USER)
    assert len(vectors) == 2 and len(vectors[0]) == 1536

    rows = await UsageRecordRepository(session, user_id).list()
    assert {(r.purpose, r.trigger) for r in rows} == {
        ("rolling_summary", "background"),
        ("embedding", "user"),
    }


async def test_count_tokens_uses_the_backend(
    session: AsyncSession, gateway: Gateway, user_id: uuid.UUID
) -> None:
    gpt = await model(session, "openai/gpt-5.6")
    short = gateway.count_tokens(gpt, [{"role": "user", "content": "hi"}])
    long = gateway.count_tokens(gpt, [{"role": "user", "content": "hi " * 400}])
    assert 0 < short < long


async def test_logs_hold_no_prompt_reply_or_key(
    session: AsyncSession,
    gateway: Gateway,
    fake: FakeProvider,
    user_id: uuid.UUID,
    caplog: pytest.LogCaptureFixture,
) -> None:
    gpt = await model(session, "openai/gpt-5.6")
    await add_key(session, user_id, "openai", OPENAI_KEY)
    with caplog.at_level(logging.DEBUG):
        await collect(gateway, session, user_id, gpt.id)
    assert "llm call model=openai/gpt-5.6 purpose=chat" in caplog.text  # metadata is logged
    for secret in (SECRET_PROMPT, fake.default_reply, OPENAI_KEY, OPENAI_KEY[-12:]):
        assert secret not in caplog.text
