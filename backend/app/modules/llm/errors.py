"""Typed gateway errors (rules.md #51). Code outside `llm` catches only these, never a
provider-specific exception. Messages never contain keys, prompts or provider error text."""

from app.core.errors import AppError


class LLMError(AppError):
    status_code = 502
    code = "llm_error"
    # A short, safe summary of the provider's error payload for the usage row: structured
    # fields only (HTTP status, provider status, quota id, retry delay), never free text.
    provider_detail: str | None = None


class RateLimited(LLMError):
    """A short rate limit: waiting and retrying can help."""

    status_code = 429
    code = "rate_limited"
    # How long the provider asked us to wait (Retry-After or its own retry delay), if it did.
    retry_after_seconds: float | None = None


class QuotaExhausted(LLMError):
    """The provider's quota is used up (for example a per-day quota), or it asked for a wait
    longer than LLM_QUOTA_EXHAUSTED_MIN_WAIT_SECONDS. Retrying soon cannot help, so callers
    never retry it. Not a subclass of RateLimited for that reason."""

    status_code = 429
    code = "quota_exhausted"


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
