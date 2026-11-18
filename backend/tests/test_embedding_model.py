"""Embedding model choice, provider arguments and the fake's word vectors. No keys, no network."""

import math

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.modules.llm.catalog import seed_default_models
from app.modules.llm.fake import FakeProvider, word_vector
from app.modules.llm.gateway import Gateway
from app.modules.llm.litellm_backend import embed_kwargs
from app.modules.llm.repository import (
    ModelConfigRepository,
    ProviderCredentialRepository,
    UsageRecordRepository,
    UserModelSettingsRepository,
)
from app.modules.llm.service import (
    ModelUnavailable,
    NoCredential,
    UsageTrigger,
    get_embedding_model,
)
from tests.graph import make_user

GEMINI = "gemini/gemini-embedding-001"


def cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))


def test_word_vectors_are_unit_length_and_deterministic() -> None:
    a = word_vector("health check timeout", 64)
    assert a == word_vector("health check timeout", 64)
    assert math.isclose(sum(v * v for v in a), 1.0)
    assert math.isclose(sum(v * v for v in word_vector("", 64)), 1.0)


def test_shared_words_mean_higher_similarity() -> None:
    query = word_vector("where is the health check timeout", 256)
    close = word_vector("def health_check(timeout): the health check", 256)
    far = word_vector("render the login button in blue", 256)
    assert cosine(query, close) > cosine(query, far)


def test_gemini_gets_task_type_and_dimensions() -> None:
    assert embed_kwargs(GEMINI, 1536, "document") == {
        "dimensions": 1536,
        "task_type": "RETRIEVAL_DOCUMENT",
    }
    assert embed_kwargs(GEMINI, 1536, "query")["task_type"] == "CODE_RETRIEVAL_QUERY"


def test_other_providers_get_only_what_they_support() -> None:
    assert embed_kwargs("openai/text-embedding-3-small", 1536, "query") == {"dimensions": 1536}
    assert embed_kwargs("openai/text-embedding-ada-002", 1536, "query") == {}
    assert embed_kwargs("voyage/voyage-4-lite", 1024, "document") == {"dimensions": 1024}
    assert embed_kwargs("mistral/mistral-embed", 1024, None) == {}


@pytest.mark.db
async def test_gateway_sends_catalog_dimensions_and_input_type(session: AsyncSession) -> None:
    await seed_default_models(session)
    user_id = await make_user(session, "Emb")
    await ProviderCredentialRepository(session, user_id).add_key(
        provider="google", api_key="test-google-key-0000"
    )
    model = await ModelConfigRepository(session).get_by_litellm_model(GEMINI)
    assert model is not None and model.enabled
    fake = FakeProvider()
    vectors = await Gateway(fake).embed(
        session, user_id, model.id, ["a b"], trigger=UsageTrigger.USER, input_type="query"
    )
    assert len(vectors[0]) == settings.embedding_dimensions
    assert fake.calls[0].input_type == "query"
    [usage] = await UsageRecordRepository(session, user_id).list()
    assert (usage.purpose, usage.trigger) == ("embedding", "user")


@pytest.mark.db
async def test_default_embedding_model_is_gemini(session: AsyncSession) -> None:
    await seed_default_models(session)
    user_id = await make_user(session, "Emb")
    with pytest.raises(NoCredential):
        await get_embedding_model(session, user_id)
    await ProviderCredentialRepository(session, user_id).add_key(
        provider="google", api_key="test-google-key-0000"
    )
    info = await get_embedding_model(session, user_id)
    assert (info.litellm_model, info.dimensions) == (GEMINI, 1536)


@pytest.mark.db
async def test_user_setting_wins_and_disabled_model_is_refused(session: AsyncSession) -> None:
    await seed_default_models(session)
    user_id = await make_user(session, "Emb")
    await ProviderCredentialRepository(session, user_id).add_key(
        provider="openai", api_key="sk-test-openai-0000"
    )
    openai = await ModelConfigRepository(session).get_by_litellm_model(
        "openai/text-embedding-3-small"
    )
    assert openai is not None
    await UserModelSettingsRepository(session, user_id).add(embedding_model_id=openai.id)
    assert (await get_embedding_model(session, user_id)).id == openai.id

    openai.enabled = False
    await session.flush()
    with pytest.raises(ModelUnavailable):
        await get_embedding_model(session, user_id)
