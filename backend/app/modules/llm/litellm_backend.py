"""The real backend: LiteLLM. The only file in the project that imports `litellm` (rule 7).

`litellm` takes several seconds to import, so it is imported on first use, not at startup.
"""

import logging
import os
from collections.abc import AsyncIterator, Mapping
from functools import cache
from types import ModuleType
from typing import Any

from app.core.config import settings
from app.modules.llm.backend import (
    ChatMessages,
    EmbedInputType,
    EmbedResult,
    StreamItem,
    TextDelta,
    UsageInfo,
)
from app.modules.llm.errors import (
    AuthFailed,
    ContextTooLong,
    LLMError,
    ProviderUnavailable,
    QuotaExhausted,
    RateLimited,
)
from app.modules.llm.provider_errors import (
    ProviderErrorInfo,
    info_from_payload,
    is_quota_exhausted,
    payload_from_text,
    retry_after_from_headers,
)

logger = logging.getLogger(__name__)


@cache
def _litellm() -> ModuleType:
    # Use the model data bundled with the package; never download it at import time.
    os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")
    import litellm

    litellm.suppress_debug_info = True  # no verbose/debug output (security.md #6)
    litellm.telemetry = False
    logging.getLogger("LiteLLM").setLevel(logging.WARNING)
    return litellm


def root_error(exc: BaseException) -> BaseException:
    """Follow wrappers to the real error. LiteLLM wraps an error that arrives mid-stream in
    MidStreamFallbackError (a ServiceUnavailableError) and keeps the real one in
    `original_exception`; a rate limit inside must still be reported as a rate limit."""
    seen: set[int] = set()
    while id(exc) not in seen:
        seen.add(id(exc))
        inner = getattr(exc, "original_exception", None)
        if not isinstance(inner, BaseException):
            break
        exc = inner
    return exc


def status_code(exc: BaseException) -> int | None:
    code = getattr(exc, "status_code", None)
    return code if isinstance(code, int) else None


def _headers(exc: BaseException) -> dict[str, str]:
    """Response headers LiteLLM kept on the error (OpenAI and Anthropic keep them; Gemini
    errors get a new, empty response)."""
    out: dict[str, str] = {}
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None)
    for source in (headers, getattr(exc, "headers", None)):
        if isinstance(source, Mapping):  # httpx.Headers is a Mapping
            out.update({str(k): str(v) for k, v in source.items()})
    return out


def provider_error_info(exc: BaseException) -> ProviderErrorInfo:
    """Structured fields of the provider's error, from the inner and the outer exception."""
    root = root_error(exc)
    payload = None
    retry_after = None
    for candidate in (root, exc):
        if retry_after is None:
            retry_after = retry_after_from_headers(_headers(candidate))
        if payload is None:
            message = getattr(candidate, "message", None)
            for text in (message if isinstance(message, str) else "", str(candidate)):
                payload = payload_from_text(text) if text else None
                if payload is not None:
                    break
    return info_from_payload(
        payload,
        http_status=status_code(root) or status_code(exc),
        header_retry_after=retry_after,
    )


def _rate_limit(info: ProviderErrorInfo, details: dict[str, Any]) -> LLMError:
    if is_quota_exhausted(info, settings.llm_quota_exhausted_min_wait_seconds):
        return QuotaExhausted(
            "The provider's quota for this model is used up (for example its daily limit). "
            "Try again after the provider resets the quota, or switch to another provider.",
            details=details,
        )
    error = RateLimited("The provider is rate limiting requests.", details=details)
    error.retry_after_seconds = info.retry_after_seconds
    return error


def map_provider_error(exc: Exception, model: str) -> LLMError:
    """Map a LiteLLM/provider exception to a typed gateway error (rule 51).

    Checks the innermost error first, then the HTTP status of the inner and the outer error.
    The provider's own message is never copied: it can echo request content. A rate limit is
    QuotaExhausted only when the payload says so (a per-day quota id, or a requested wait over
    LLM_QUOTA_EXHAUSTED_MIN_WAIT_SECONDS); anything else stays an ordinary RateLimited.
    """
    mapped = _map(exc, model)
    mapped.provider_detail = provider_error_info(exc).detail()
    return mapped


def _map(exc: Exception, model: str) -> LLMError:
    litellm = _litellm()
    details: dict[str, Any] = {"model": model}
    for candidate in (root_error(exc), exc):
        if isinstance(candidate, litellm.ContextWindowExceededError):
            return ContextTooLong("The request is too long for this model.", details=details)
        if isinstance(candidate, litellm.RateLimitError):
            return _rate_limit(provider_error_info(exc), details)
        if isinstance(candidate, litellm.AuthenticationError | litellm.PermissionDeniedError):
            return AuthFailed("The provider rejected the API key.", details=details)
    for candidate in (root_error(exc), exc):
        code = status_code(candidate)
        if code == 429:
            return _rate_limit(provider_error_info(exc), details)
        if code in (401, 403):
            return AuthFailed("The provider rejected the API key.", details=details)
    return ProviderUnavailable("The provider could not answer.", details=details)


def _log_provider_error(exc: Exception, model: str) -> None:
    # Type names and the HTTP status only: never the message, which can echo content.
    # The detail holds sanitized structured fields only (see provider_errors.py).
    root = root_error(exc)
    logger.warning(
        "provider error type=%s root=%s status=%s model=%s detail=%s",
        type(exc).__name__,
        type(root).__name__,
        status_code(root) or status_code(exc),
        model,
        provider_error_info(exc).detail(),
    )


# Models whose output size can be chosen. LiteLLM 1.110.0 maps `dimensions` to
# `outputDimensionality` for Gemini and to `output_dimension` for Voyage; OpenAI takes it as
# is, but only from text-embedding-3 on. Sending it to other models is an error.
_SETTABLE_DIMENSIONS = ("gemini/", "voyage/", "openai/text-embedding-3")

# Gemini embeds documents and queries differently. LiteLLM 1.110.0 passes `task_type` through
# as `taskType`; both values are in its own TaskType enum. CODE_RETRIEVAL_QUERY is Google's
# type for a plain-language question about code, matched against RETRIEVAL_DOCUMENT vectors.
_GEMINI_TASK_TYPES = {"document": "RETRIEVAL_DOCUMENT", "query": "CODE_RETRIEVAL_QUERY"}


def embed_kwargs(
    model: str, dimensions: int | None, input_type: EmbedInputType | None
) -> dict[str, Any]:
    """Provider-specific embedding arguments. No network."""
    kwargs: dict[str, Any] = {}
    if dimensions is not None and model.startswith(_SETTABLE_DIMENSIONS):
        kwargs["dimensions"] = dimensions
    if input_type is not None and model.startswith("gemini/"):
        kwargs["task_type"] = _GEMINI_TASK_TYPES[input_type]
    return kwargs


class LiteLLMBackend:
    async def stream_chat(
        self, model: str, messages: ChatMessages, *, api_key: str, max_tokens: int | None
    ) -> AsyncIterator[StreamItem]:
        litellm = _litellm()
        kwargs: dict[str, Any] = {"stream_options": {"include_usage": True}}
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        try:
            response = await litellm.acompletion(
                model=model, messages=messages, api_key=api_key, stream=True, **kwargs
            )
            async for part in response:
                choices = getattr(part, "choices", None) or []
                text = choices[0].delta.content if choices else None
                if text:
                    yield TextDelta(text)
                usage = getattr(part, "usage", None)
                if usage:
                    yield UsageInfo(usage.prompt_tokens or 0, usage.completion_tokens or 0)
        except LLMError:
            raise
        except Exception as exc:
            _log_provider_error(exc, model)
            raise map_provider_error(exc, model) from None

    async def embed(
        self,
        model: str,
        texts: list[str],
        *,
        api_key: str,
        dimensions: int | None = None,
        input_type: EmbedInputType | None = None,
    ) -> EmbedResult:
        litellm = _litellm()
        kwargs = embed_kwargs(model, dimensions, input_type)
        try:
            response = await litellm.aembedding(model=model, input=texts, api_key=api_key, **kwargs)
        except Exception as exc:
            _log_provider_error(exc, model)
            raise map_provider_error(exc, model) from None
        vectors = [item["embedding"] for item in response.data]
        usage = getattr(response, "usage", None)
        return EmbedResult(vectors=vectors, input_tokens=getattr(usage, "prompt_tokens", 0) or 0)

    def count_tokens(self, model: str, messages: ChatMessages) -> int:
        return int(_litellm().token_counter(model=model, messages=messages))
