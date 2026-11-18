"""Public interface of the llm module. Other modules and the app use only this file (rule 6)."""

from functools import cache

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
from app.modules.llm.models import ModelKind, UsagePurpose, UsageTrigger


@cache
def _default_gateway() -> Gateway:
    from app.modules.llm.litellm_backend import LiteLLMBackend

    return Gateway(LiteLLMBackend())


def get_gateway() -> Gateway:
    """FastAPI dependency: the real gateway. Tests override it with a FakeProvider gateway."""
    return _default_gateway()


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
    "ModelKind",
    "ModelUnavailable",
    "NoCredential",
    "ProviderUnavailable",
    "RateLimited",
    "UsageLinks",
    "UsagePurpose",
    "UsageTrigger",
    "get_gateway",
    "key_hint",
    "seed_default_models",
    "validate_master_key",
]
