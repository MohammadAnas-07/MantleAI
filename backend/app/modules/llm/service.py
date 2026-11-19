"""Public interface of the llm module. Other modules and the app use only this file (rule 6)."""

import uuid
from dataclasses import dataclass
from decimal import Decimal
from functools import cache

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.modules.llm.backend import Backend, ChatMessages, EmbedInputType
from app.modules.llm.catalog import seed_default_models
from app.modules.llm.crypto import MasterKeyError, key_hint, validate_master_key
from app.modules.llm.errors import (
    AuthFailed,
    ContextTooLong,
    LLMError,
    ModelUnavailable,
    NoCredential,
    ProviderUnavailable,
    QuotaExhausted,
    RateLimited,
)
from app.modules.llm.gateway import ChatDelta, ChatDone, ChatEvent, Gateway, UsageLinks
from app.modules.llm.models import ModelConfig, ModelKind, UsagePurpose, UsageTrigger
from app.modules.llm.repository import (
    ModelConfigRepository,
    ProviderCredentialRepository,
    UserModelSettingsRepository,
)


@cache
def _default_gateway() -> Gateway:
    from app.modules.llm.litellm_backend import LiteLLMBackend

    return Gateway(LiteLLMBackend())


def get_gateway() -> Gateway:
    """FastAPI dependency: the real gateway. Tests override it with a FakeProvider gateway."""
    return _default_gateway()


@dataclass(frozen=True)
class ModelInfo:
    """What other modules may know about a model."""

    id: uuid.UUID
    provider: str
    litellm_model: str
    display_name: str
    context_window: int
    max_output_tokens: int | None
    supports_tools: bool


@dataclass(frozen=True)
class EmbeddingModelInfo:
    """What other modules may know about an embedding model."""

    id: uuid.UUID
    provider: str
    litellm_model: str
    display_name: str
    dimensions: int
    max_input_tokens: int
    input_cost_per_mtok: Decimal | None


@dataclass(frozen=True)
class ModelSettings:
    utility_model_id: uuid.UUID | None  # None = use the conversation's active model
    background_summary_enabled: bool


def _info(model: ModelConfig) -> ModelInfo:
    return ModelInfo(
        id=model.id,
        provider=model.provider,
        litellm_model=model.litellm_model,
        display_name=model.display_name,
        context_window=model.context_window,
        max_output_tokens=model.max_output_tokens,
        supports_tools=model.supports_tools,
    )


async def get_chat_model(session: AsyncSession, model_id: uuid.UUID) -> ModelInfo:
    """An enabled chat model, or ModelUnavailable."""
    model = await ModelConfigRepository(session).get(model_id)
    if model is None or not model.enabled or model.kind != ModelKind.CHAT:
        raise ModelUnavailable("This model doesn't exist, is disabled, or isn't a chat model.")
    return _info(model)


async def list_chat_models(session: AsyncSession) -> list[ModelInfo]:
    rows = await ModelConfigRepository(session).list(kind=ModelKind.CHAT, enabled=True, limit=500)
    return [_info(m) for m in rows]


async def providers_with_keys(session: AsyncSession, user_id: uuid.UUID) -> set[str]:
    return await ProviderCredentialRepository(session, user_id).providers_with_keys()


async def get_model_settings(session: AsyncSession, user_id: uuid.UUID) -> ModelSettings:
    row = await UserModelSettingsRepository(session, user_id).get_for_user()
    if row is None:
        return ModelSettings(utility_model_id=None, background_summary_enabled=True)
    return ModelSettings(row.utility_model_id, row.background_summary_enabled)


async def get_embedding_model(
    session: AsyncSession, user_id: uuid.UUID, *, require_key: bool = True
) -> EmbeddingModelInfo:
    """The user's embedding model: their setting, else `DEFAULT_EMBEDDING_MODEL`.

    Raises ModelUnavailable when it is missing, disabled, or its dimension doesn't match the
    vector column, and (with `require_key`) NoCredential when the user has no key for its
    provider.
    """
    models = ModelConfigRepository(session)
    row = await UserModelSettingsRepository(session, user_id).get_for_user()
    model = None
    if row is not None and row.embedding_model_id is not None:
        model = await models.get(row.embedding_model_id)
    if model is None:
        found = await models.list(litellm_model=settings.default_embedding_model, limit=1)
        model = found[0] if found else None
    if (
        model is None
        or not model.enabled
        or model.kind != ModelKind.EMBEDDING
        or model.embedding_dimensions != settings.embedding_dimensions
    ):
        raise ModelUnavailable(
            "Pick an enabled embedding model in /api/v1/settings/models before indexing."
        )
    if require_key and model.provider not in await providers_with_keys(session, user_id):
        raise NoCredential(
            f"Add an API key for {model.provider} to index with {model.display_name}.",
            details={"provider": model.provider},
        )
    return EmbeddingModelInfo(
        id=model.id,
        provider=model.provider,
        litellm_model=model.litellm_model,
        display_name=model.display_name,
        dimensions=model.embedding_dimensions,
        max_input_tokens=model.context_window,
        input_cost_per_mtok=model.input_cost_per_mtok,
    )


def count_tokens(gateway: Gateway, model: ModelInfo, messages: ChatMessages) -> int:
    """Estimated prompt tokens of `messages` for `model` (no network)."""
    return gateway.backend.count_tokens(model.litellm_model, messages)


__all__ = [
    "AuthFailed",
    "Backend",
    "ChatDelta",
    "ChatDone",
    "ChatEvent",
    "ChatMessages",
    "ContextTooLong",
    "EmbedInputType",
    "EmbeddingModelInfo",
    "Gateway",
    "LLMError",
    "MasterKeyError",
    "ModelInfo",
    "ModelKind",
    "ModelSettings",
    "ModelUnavailable",
    "NoCredential",
    "ProviderUnavailable",
    "QuotaExhausted",
    "RateLimited",
    "UsageLinks",
    "UsagePurpose",
    "UsageTrigger",
    "count_tokens",
    "get_chat_model",
    "get_embedding_model",
    "get_embedding_model_by_id",
    "get_gateway",
    "get_model_settings",
    "key_hint",
    "list_chat_models",
    "providers_with_keys",
    "seed_default_models",
    "validate_master_key",
]


async def get_embedding_model_by_id(
    session: AsyncSession, model_id: uuid.UUID
) -> EmbeddingModelInfo:
    """An enabled embedding model by id (for a job that snapshotted it), or ModelUnavailable."""
    model = await ModelConfigRepository(session).get(model_id)
    if model is None or not model.enabled or model.kind != ModelKind.EMBEDDING:
        raise ModelUnavailable("The embedding model of this index run is gone or disabled.")
    return EmbeddingModelInfo(
        id=model.id,
        provider=model.provider,
        litellm_model=model.litellm_model,
        display_name=model.display_name,
        dimensions=model.embedding_dimensions or 0,
        max_input_tokens=model.context_window,
        input_cost_per_mtok=model.input_cost_per_mtok,
    )
