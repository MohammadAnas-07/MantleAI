"""Public interface of the llm module. Other modules and the app use only this file (rule 6)."""

import uuid
from dataclasses import dataclass
from functools import cache

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.llm.backend import Backend, ChatMessages
from app.modules.llm.catalog import seed_default_models
from app.modules.llm.crypto import MasterKeyError, key_hint, validate_master_key
from app.modules.llm.errors import (
    AuthFailed,
    ContextTooLong,
    LLMError,
    ModelUnavailable,
    NoCredential,
    ProviderUnavailable,
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
    "Gateway",
    "LLMError",
    "MasterKeyError",
    "ModelInfo",
    "ModelKind",
    "ModelSettings",
    "ModelUnavailable",
    "NoCredential",
    "ProviderUnavailable",
    "RateLimited",
    "UsageLinks",
    "UsagePurpose",
    "UsageTrigger",
    "count_tokens",
    "get_chat_model",
    "get_gateway",
    "get_model_settings",
    "key_hint",
    "list_chat_models",
    "providers_with_keys",
    "seed_default_models",
    "validate_master_key",
]
