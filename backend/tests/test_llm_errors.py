"""Provider errors map to typed gateway errors (rule 51). Imports litellm, but makes no call."""

import logging
from collections.abc import Callable
from typing import Any

import httpx
import pytest

from app.modules.llm.errors import (
    AuthFailed,
    ContextTooLong,
    LLMError,
    ProviderUnavailable,
    QuotaExhausted,
    RateLimited,
)
from app.modules.llm.litellm_backend import LiteLLMBackend, _litellm, map_provider_error

PROVIDER_TEXT = "secret prompt text echoed by the provider"


def make(name: str) -> Exception:
    cls = getattr(_litellm(), name)
    kwargs: dict[str, Any] = {"message": PROVIDER_TEXT, "llm_provider": "openai", "model": "gpt-x"}
    if name == "PermissionDeniedError":  # this one also needs an HTTP response
        request = httpx.Request("POST", "https://example.invalid")
        kwargs["response"] = httpx.Response(403, request=request)
    return cls(**kwargs)


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("ContextWindowExceededError", ContextTooLong),
        ("RateLimitError", RateLimited),
        ("AuthenticationError", AuthFailed),
        ("PermissionDeniedError", AuthFailed),
        ("APIConnectionError", ProviderUnavailable),
        ("ServiceUnavailableError", ProviderUnavailable),
        ("InternalServerError", ProviderUnavailable),
    ],
)
def test_maps_litellm_errors(name: str, expected: type[LLMError]) -> None:
    mapped = map_provider_error(make(name), "openai/gpt-x")
    assert type(mapped) is expected
    assert PROVIDER_TEXT not in mapped.message


def mid_stream(original: Exception | None) -> Exception:
    from litellm.exceptions import MidStreamFallbackError

    return MidStreamFallbackError(
        message=PROVIDER_TEXT, model="gpt-x", llm_provider="gemini", original_exception=original
    )


class StatusOnly(Exception):
    """A provider error that LiteLLM didn't map to a type, only an HTTP status."""

    def __init__(self, status_code: int) -> None:
        super().__init__(PROVIDER_TEXT)
        self.status_code = status_code


@pytest.mark.parametrize(
    ("inner", "expected"),
    [
        (lambda: make("RateLimitError"), RateLimited),
        (lambda: make("AuthenticationError"), AuthFailed),
        (lambda: make("ContextWindowExceededError"), ContextTooLong),
        (lambda: StatusOnly(429), RateLimited),
        (lambda: StatusOnly(401), AuthFailed),
        (lambda: StatusOnly(500), ProviderUnavailable),
        (lambda: None, ProviderUnavailable),
    ],
)
def test_mid_stream_errors_are_unwrapped(
    inner: Callable[[], Exception | None], expected: type[LLMError]
) -> None:
    # Regression: a Gemini rate limit during a stream arrived as MidStreamFallbackError (a
    # ServiceUnavailableError) and was reported as provider_unavailable.
    mapped = map_provider_error(mid_stream(inner()), "gemini/x")
    assert type(mapped) is expected
    assert PROVIDER_TEXT not in mapped.message


async def test_mid_stream_rate_limit_is_logged_with_status_not_text(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    async def failing(**_: Any) -> None:
        raise mid_stream(StatusOnly(429))

    monkeypatch.setattr(_litellm(), "acompletion", failing)
    stream = LiteLLMBackend().stream_chat("gemini/x", [], api_key="k", max_tokens=1)
    with caplog.at_level(logging.WARNING), pytest.raises(RateLimited):
        await anext(stream)
    assert "type=MidStreamFallbackError root=StatusOnly status=429" in caplog.text
    assert PROVIDER_TEXT not in caplog.text


def gemini_rate_limit(quota_id: str | None, retry_delay: str | None) -> Exception:
    """A LiteLLM RateLimitError as LiteLLM 1.110.0 builds it for Gemini: the body is only in
    the message text, the HTTP response is new and empty. The body follows the google.rpc
    error model; it is not captured from a real exhausted quota."""
    import json

    details: list[dict[str, object]] = []
    if quota_id:
        details.append({"@type": "type.googleapis.com/google.rpc.QuotaFailure",
                        "violations": [{"quotaId": quota_id}]})  # fmt: skip
    if retry_delay:
        details.append({"@type": "type.googleapis.com/google.rpc.RetryInfo",
                        "retryDelay": retry_delay})  # fmt: skip
    body = {"error": {"code": 429, "message": PROVIDER_TEXT, "status": "RESOURCE_EXHAUSTED",
                      "details": details}}  # fmt: skip
    cls = _litellm().RateLimitError
    return cls(message=f"geminiException - {json.dumps(body)}", llm_provider="gemini",
               model="gemini-embedding-001")  # fmt: skip


def test_gemini_per_day_quota_is_quota_exhausted() -> None:
    exc = gemini_rate_limit("EmbedContentRequestsPerDayPerUserPerProjectPerModel-FreeTier", "40s")
    mapped = map_provider_error(exc, "gemini/gemini-embedding-001")
    assert type(mapped) is QuotaExhausted and mapped.code == "quota_exhausted"
    assert "resets the quota" in mapped.message
    assert mapped.provider_detail is not None
    assert "quota_id=EmbedContentRequestsPerDayPerUserPerProjectPerModel-FreeTier" in (
        mapped.provider_detail
    )
    assert PROVIDER_TEXT not in mapped.message and PROVIDER_TEXT not in mapped.provider_detail


def test_gemini_per_minute_limit_is_a_rate_limit_with_its_delay() -> None:
    exc = gemini_rate_limit("EmbedContentRequestsPerMinutePerProjectPerModel-FreeTier", "33s")
    mapped = map_provider_error(exc, "gemini/x")
    assert type(mapped) is RateLimited
    assert mapped.retry_after_seconds == 33.0


def test_long_requested_wait_is_quota_exhausted(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.config import settings

    exc = gemini_rate_limit(None, "900s")
    assert type(map_provider_error(exc, "gemini/x")) is QuotaExhausted
    monkeypatch.setattr(settings, "llm_quota_exhausted_min_wait_seconds", 1000.0)
    assert type(map_provider_error(exc, "gemini/x")) is RateLimited


def test_rate_limit_without_payload_stays_a_rate_limit() -> None:
    for exc in (make("RateLimitError"), StatusOnly(429), mid_stream(StatusOnly(429))):
        mapped = map_provider_error(exc, "gemini/x")
        assert type(mapped) is RateLimited
        assert mapped.retry_after_seconds is None
        assert mapped.provider_detail == "http=429"


def test_retry_after_header_is_read() -> None:
    request = httpx.Request("POST", "https://example.invalid")
    response = httpx.Response(429, request=request, headers={"retry-after": "7"})
    exc = _litellm().RateLimitError(
        message=PROVIDER_TEXT, llm_provider="openai", model="gpt-x", response=response
    )
    mapped = map_provider_error(exc, "openai/gpt-x")
    assert type(mapped) is RateLimited and mapped.retry_after_seconds == 7.0
    assert mapped.provider_detail == "http=429 retry_after_s=7"


def test_unknown_errors_become_provider_unavailable() -> None:
    assert isinstance(map_provider_error(ValueError("boom"), "m"), ProviderUnavailable)


async def test_backend_raises_typed_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    async def failing(**_: Any) -> None:
        raise make("RateLimitError")

    monkeypatch.setattr(_litellm(), "acompletion", failing)
    stream = LiteLLMBackend().stream_chat("openai/gpt-x", [], api_key="k", max_tokens=1)
    with pytest.raises(RateLimited) as info:
        await anext(stream)
    assert info.value.__cause__ is None  # the provider exception (and its text) is dropped


async def test_backend_streams_text_and_usage(monkeypatch: pytest.MonkeyPatch) -> None:
    class Delta:
        def __init__(self, content: str | None) -> None:
            self.content = content

    class Choice:
        def __init__(self, content: str | None) -> None:
            self.delta = Delta(content)

    class Usage:
        prompt_tokens, completion_tokens = 7, 3

    class Part:
        def __init__(self, content: str | None, usage: Any = None) -> None:
            self.choices = [Choice(content)] if content is not None else []
            self.usage = usage

    async def fake_stream() -> Any:
        for part in [Part("Hel"), Part("lo"), Part(None, Usage())]:
            yield part

    captured: dict[str, Any] = {}

    async def acompletion(**kwargs: Any) -> Any:
        captured.update(kwargs)
        return fake_stream()

    monkeypatch.setattr(_litellm(), "acompletion", acompletion)
    backend = LiteLLMBackend()
    items = [i async for i in backend.stream_chat("openai/gpt-x", [], api_key="k", max_tokens=5)]

    assert [getattr(i, "text", None) for i in items[:2]] == ["Hel", "lo"]
    assert (items[2].input_tokens, items[2].output_tokens) == (7, 3)  # type: ignore[union-attr]
    assert captured["stream"] is True and captured["max_tokens"] == 5


def test_litellm_debug_output_is_off() -> None:
    litellm = _litellm()
    assert litellm.suppress_debug_info is True
    assert litellm.telemetry is False


def test_only_the_llm_module_imports_litellm() -> None:
    from pathlib import Path

    app_dir = Path(__file__).resolve().parents[1] / "app"
    offenders: list[str] = []
    check: Callable[[str], bool] = lambda line: (  # noqa: E731
        line.strip().startswith(("import litellm", "from litellm"))
    )
    for path in app_dir.rglob("*.py"):
        if path.name == "litellm_backend.py":
            continue
        if any(check(line) for line in path.read_text(encoding="utf-8").splitlines()):
            offenders.append(str(path))
    assert offenders == []
