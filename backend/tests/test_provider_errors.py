"""Reading a provider's error payload, and telling a used-up quota from a short rate limit.
Pure functions: no litellm, no network.

The Gemini payloads below follow the google.rpc error model (QuotaFailure, RetryInfo). They
are not captured from a real exhausted quota; `usage_records.error_detail` will show the real
fields the next time it happens.
"""

import json
from datetime import UTC, datetime

import pytest

from app.modules.llm.provider_errors import (
    ProviderErrorInfo,
    info_from_payload,
    is_quota_exhausted,
    parse_duration,
    parse_retry_after,
    payload_from_text,
    retry_after_from_headers,
)

SECRET = "def secret_function(): pass  # prompt text"


def gemini_payload(quota_id: str | None, retry_delay: str | None) -> dict[str, object]:
    details: list[dict[str, object]] = []
    if quota_id is not None:
        details.append(
            {
                "@type": "type.googleapis.com/google.rpc.QuotaFailure",
                "violations": [{"quotaMetric": "generativelanguage.googleapis.com/x",
                                "quotaId": quota_id}],
            }
        )  # fmt: skip
    if retry_delay is not None:
        details.append(
            {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": retry_delay}
        )
    return {
        "error": {
            "code": 429,
            "message": f"Quota exceeded. {SECRET}",
            "status": "RESOURCE_EXHAUSTED",
            "details": details,
        }
    }


def litellm_text(payload: dict[str, object]) -> str:
    # How LiteLLM puts the body into the message: a prefix, then the raw JSON.
    return f"litellm.RateLimitError: geminiException - {json.dumps(payload, indent=2)}"


def info_for(quota_id: str | None, retry_delay: str | None) -> ProviderErrorInfo:
    payload = payload_from_text(litellm_text(gemini_payload(quota_id, retry_delay)))
    return info_from_payload(payload, http_status=429)


def test_per_day_quota_id_is_quota_exhausted() -> None:
    info = info_for("EmbedContentRequestsPerDayPerUserPerProjectPerModel-FreeTier", "40s")
    assert info.quota_ids == ("EmbedContentRequestsPerDayPerUserPerProjectPerModel-FreeTier",)
    assert info.provider_status == "RESOURCE_EXHAUSTED" and info.provider_code == "429"
    assert is_quota_exhausted(info, 600)


def test_per_minute_quota_with_short_delay_is_a_rate_limit() -> None:
    info = info_for("EmbedContentRequestsPerMinutePerProjectPerModel-FreeTier", "33s")
    assert info.retry_after_seconds == 33.0
    assert not is_quota_exhausted(info, 600)


def test_wait_longer_than_the_setting_is_quota_exhausted() -> None:
    info = info_for(None, "3600s")
    assert is_quota_exhausted(info, 600)
    assert not is_quota_exhausted(info, 7200)


def test_unknown_error_stays_a_rate_limit() -> None:
    # RESOURCE_EXHAUSTED alone, no quota id, no delay: not enough to call it a used-up quota.
    info = info_for(None, None)
    assert info.provider_status == "RESOURCE_EXHAUSTED"
    assert not is_quota_exhausted(info, 600)
    assert not is_quota_exhausted(info_from_payload(None, http_status=429), 600)
    assert payload_from_text("429 Too Many Requests, no JSON here") is None


def test_detail_has_structured_fields_only() -> None:
    info = info_for("GenerateRequestsPerDayPerProjectPerModel-FreeTier", "20.5s")
    detail = info.detail()
    assert detail == (
        "http=429 status=RESOURCE_EXHAUSTED code=429 "
        "quota_id=GenerateRequestsPerDayPerProjectPerModel-FreeTier retry_after_s=20.5"
    )
    assert "secret" not in detail and "Quota exceeded" not in detail


def test_detail_strips_unsafe_characters_and_is_short() -> None:
    info = ProviderErrorInfo(
        http_status=429,
        provider_status='BAD <b>"x"</b>\n',
        quota_ids=tuple(f"{i}{'q' * 500}" for i in range(5)),
    )
    detail = info.detail()
    assert detail is not None and len(detail) <= 255
    assert detail.startswith("http=429 status=BADbx/b ")
    assert not any(c in detail for c in '<>"\n')
    assert detail.count("quota_id=") <= 3


@pytest.mark.parametrize(
    ("value", "seconds"),
    [("33s", 33.0), ("1.5s", 1.5), ("20", 20.0), (7, 7.0), ({"seconds": 2, "nanos": 5e8}, 2.5),
     ("soon", None), (-1, None), (True, None)],
)  # fmt: skip
def test_parse_duration(value: object, seconds: float | None) -> None:
    assert parse_duration(value) == seconds


def test_retry_after_header_seconds_ms_and_http_date() -> None:
    assert retry_after_from_headers({"Retry-After": "12"}) == 12.0
    assert retry_after_from_headers({"retry-after-ms": "1500"}) == 1.5
    assert retry_after_from_headers({}) is None
    now = datetime(2026, 11, 19, 12, 0, 0, tzinfo=UTC)
    assert parse_retry_after("Thu, 19 Nov 2026 12:02:00 GMT", now) == 120.0


def test_header_wins_over_payload_delay() -> None:
    payload = gemini_payload(None, "33s")
    info = info_from_payload(payload, http_status=429, header_retry_after=5.0)
    assert info.retry_after_seconds == 5.0
