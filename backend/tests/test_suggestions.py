import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.llm.repository import ModelConfigRepository, ProviderCredentialRepository
from app.modules.llm.service import get_chat_model, suggest_models
from tests.graph import make_user

pytestmark = pytest.mark.db


async def add_model(session: AsyncSession, name: str, provider: str, window: int) -> uuid.UUID:
    row = await ModelConfigRepository(session).add(
        provider=provider, litellm_model=f"fake/{name}-{uuid.uuid4().hex[:6]}", display_name=name,
        kind="chat", context_window=window, max_output_tokens=1000,
    )  # fmt: skip
    return row.id


async def test_suggestions_need_a_key_and_fit_the_reason(session: AsyncSession) -> None:
    user = await make_user(session, "Sam")
    small = await add_model(session, "small-openai", "openai", 8_000)
    await add_model(session, "big-openai", "openai", 200_000)
    await add_model(session, "mid-anthropic", "anthropic", 32_000)
    await add_model(session, "huge-google", "google", 1_000_000)  # no key: never suggested
    creds = ProviderCredentialRepository(session, user)
    await creds.add_key(provider="openai", api_key="sk-test-openai-000000")
    await creds.add_key(provider="anthropic", api_key="sk-test-anthro-000000")

    current = await get_chat_model(session, small)
    bigger = await suggest_models(session, user, current, "context_too_long")
    assert [s["display_name"] for s in bigger] == ["big-openai", "mid-anthropic"]

    other_provider = await suggest_models(session, user, current, "rate_limited")
    assert [s["display_name"] for s in other_provider] == ["mid-anthropic"]
