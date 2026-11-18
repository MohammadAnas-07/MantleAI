"""Typed gateway errors (rules.md #51). Code outside `llm` catches only these, never a
provider-specific exception. Messages never contain keys, prompts or provider error text."""

from app.core.errors import AppError


class LLMError(AppError):
    status_code = 502
    code = "llm_error"


class RateLimited(LLMError):
    status_code = 429
    code = "rate_limited"


class ContextTooLong(LLMError):
    status_code = 413
    code = "context_too_long"


class AuthFailed(LLMError):
    status_code = 401
    code = "auth_failed"


class ProviderUnavailable(LLMError):
    status_code = 503
    code = "provider_unavailable"


class NoCredential(LLMError):
    """The user has no key for the model's provider."""

    status_code = 422
    code = "no_credential"


class ModelUnavailable(LLMError):
    """The model doesn't exist, is disabled, or is the wrong kind for the call."""

    status_code = 422
    code = "model_unavailable"
