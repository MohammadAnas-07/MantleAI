"""The real backend: LiteLLM. The only file in the project that imports `litellm` (rule 7).

`litellm` takes several seconds to import, so it is imported on first use, not at startup.
"""

import logging
import os
from collections.abc import AsyncIterator
from functools import cache
from types import ModuleType
from typing import Any

from app.modules.llm.backend import ChatMessages, EmbedResult, StreamItem, TextDelta, UsageInfo
from app.modules.llm.errors import (
    AuthFailed,
    ContextTooLong,
    LLMError,
    ProviderUnavailable,
    RateLimited,
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


def map_provider_error(exc: Exception, model: str) -> LLMError:
    """Map a LiteLLM/provider exception to a typed gateway error (rule 51).

    Checks the innermost error first, then the HTTP status of the inner and the outer error.
    The provider's own message is never copied: it can echo request content.
    """
    litellm = _litellm()
    details = {"model": model}
    for candidate in (root_error(exc), exc):
        if isinstance(candidate, litellm.ContextWindowExceededError):
            return ContextTooLong("The request is too long for this model.", details=details)
        if isinstance(candidate, litellm.RateLimitError):
            return RateLimited("The provider is rate limiting requests.", details=details)
        if isinstance(candidate, litellm.AuthenticationError | litellm.PermissionDeniedError):
            return AuthFailed("The provider rejected the API key.", details=details)
    for candidate in (root_error(exc), exc):
        code = status_code(candidate)
        if code == 429:
            return RateLimited("The provider is rate limiting requests.", details=details)
        if code in (401, 403):
            return AuthFailed("The provider rejected the API key.", details=details)
    return ProviderUnavailable("The provider could not answer.", details=details)


def _log_provider_error(exc: Exception, model: str) -> None:
    # Type names and the HTTP status only: never the message, which can echo content.
    root = root_error(exc)
    logger.warning(
        "provider error type=%s root=%s status=%s model=%s",
        type(exc).__name__,
        type(root).__name__,
        status_code(root) or status_code(exc),
        model,
    )


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

    async def embed(self, model: str, texts: list[str], *, api_key: str) -> EmbedResult:
        litellm = _litellm()
        try:
            response = await litellm.aembedding(model=model, input=texts, api_key=api_key)
        except Exception as exc:
            _log_provider_error(exc, model)
            raise map_provider_error(exc, model) from None
        vectors = [item["embedding"] for item in response.data]
        usage = getattr(response, "usage", None)
        return EmbedResult(vectors=vectors, input_tokens=getattr(usage, "prompt_tokens", 0) or 0)

    def count_tokens(self, model: str, messages: ChatMessages) -> int:
        return int(_litellm().token_counter(model=model, messages=messages))
