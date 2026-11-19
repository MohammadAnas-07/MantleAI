"""Read the structured parts of a provider's error payload. No network, no `litellm` import.

LiteLLM keeps the provider's response body only as text inside the exception message (for
Gemini it builds a new, empty HTTP response, so headers and body are gone). We look for the
first JSON object in that text with an "error" key and take structured fields only: the
provider status and code, quota ids and a retry delay. Free text (`message`) is never kept:
it can echo the request.

Gemini/Google errors follow the google.rpc error model: `error.status` ("RESOURCE_EXHAUSTED"),
`error.details[]` with a QuotaFailure (`violations[].quotaId`) and a RetryInfo (`retryDelay`,
for example "33s"). We search the whole payload for those keys instead of fixed paths, so a
slightly different layout still works.
"""

import json
import re
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any

# Quota ids that name a daily limit, for example "...RequestsPerDayPerProjectPerModel-FreeTier".
_PER_DAY = re.compile(r"per[_-]?day|daily", re.IGNORECASE)
_UNSAFE = re.compile(r"[^A-Za-z0-9_.:/-]")
_DURATION = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*s?\s*$")
_MAX_TEXT = 20_000  # never parse more than this much error text
_MAX_TRIES = 20  # JSON start positions tried
_MAX_DETAIL = 255  # column size of usage_records.error_detail
_MAX_QUOTA_IDS = 3


def _safe(value: object, limit: int = 80) -> str:
    return _UNSAFE.sub("", str(value))[:limit]


@dataclass(frozen=True)
class ProviderErrorInfo:
    http_status: int | None = None
    provider_status: str | None = None  # e.g. RESOURCE_EXHAUSTED
    provider_code: str | None = None  # e.g. 429, or a string code such as rate_limit_exceeded
    quota_ids: tuple[str, ...] = ()
    retry_after_seconds: float | None = None

    @property
    def per_day_quota(self) -> bool:
        return any(_PER_DAY.search(q) for q in self.quota_ids)

    def detail(self) -> str | None:
        """A short line for the usage row, made only from sanitized structured fields."""
        parts: list[str] = []
        if self.http_status is not None:
            parts.append(f"http={self.http_status}")
        if self.provider_status:
            parts.append(f"status={_safe(self.provider_status)}")
        if self.provider_code:
            parts.append(f"code={_safe(self.provider_code)}")
        for quota_id in self.quota_ids[:_MAX_QUOTA_IDS]:
            parts.append(f"quota_id={_safe(quota_id)}")
        if self.retry_after_seconds is not None:
            parts.append(f"retry_after_s={self.retry_after_seconds:g}")
        return " ".join(parts)[:_MAX_DETAIL] or None


def is_quota_exhausted(info: ProviderErrorInfo, min_wait_seconds: float) -> bool:
    """True only when the payload says so: a per-day quota id, or a requested wait longer
    than `min_wait_seconds`. Everything else is an ordinary rate limit."""
    if info.per_day_quota:
        return True
    return info.retry_after_seconds is not None and info.retry_after_seconds > min_wait_seconds


def parse_duration(value: object) -> float | None:
    """ "33s", "1.5s", "20" or a number -> seconds."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value) if value >= 0 else None
    if isinstance(value, str):
        match = _DURATION.match(value)
        if match:
            return float(match.group(1))
    if isinstance(value, Mapping):  # protobuf Duration as {"seconds": ..., "nanos": ...}
        seconds = parse_duration(value.get("seconds", 0))
        nanos = value.get("nanos", 0)
        if seconds is not None and isinstance(nanos, int | float):
            return seconds + nanos / 1e9
    return None


def parse_retry_after(value: str, now: datetime | None = None) -> float | None:
    """An HTTP Retry-After value: delay in seconds, or an HTTP date."""
    seconds = parse_duration(value)
    if seconds is not None:
        return seconds
    try:
        when = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    return max((when - (now or datetime.now(UTC))).total_seconds(), 0.0)


def retry_after_from_headers(headers: Mapping[str, str] | None) -> float | None:
    if not headers:
        return None
    lowered = {str(k).lower(): str(v) for k, v in headers.items()}
    if "retry-after-ms" in lowered:
        ms = parse_duration(lowered["retry-after-ms"])
        if ms is not None:
            return ms / 1000
    if "retry-after" in lowered:
        return parse_retry_after(lowered["retry-after"])
    return None


def payload_from_text(text: str) -> dict[str, Any] | None:
    """The first JSON object in `text` that has an "error" key."""
    text = text[:_MAX_TEXT]
    decoder = json.JSONDecoder()
    start = text.find("{")
    tries = 0
    while start != -1 and tries < _MAX_TRIES:
        tries += 1
        try:
            value, _ = decoder.raw_decode(text, start)
        except ValueError:
            value = None
        if isinstance(value, dict) and "error" in value:
            return value
        start = text.find("{", start + 1)
    return None


def _walk(value: object) -> Iterator[tuple[str, object]]:
    if isinstance(value, Mapping):
        for key, inner in value.items():
            yield str(key), inner
            yield from _walk(inner)
    elif isinstance(value, list):
        for inner in value:
            yield from _walk(inner)


def info_from_payload(
    payload: Mapping[str, Any] | None,
    *,
    http_status: int | None = None,
    header_retry_after: float | None = None,
) -> ProviderErrorInfo:
    quota_ids: list[str] = []
    retry_delay: float | None = None
    status: str | None = None
    code: str | None = None
    if payload is not None:
        error = payload.get("error")
        if isinstance(error, Mapping):
            raw_status = error.get("status")
            status = raw_status if isinstance(raw_status, str) else None
            raw_code = error.get("code")
            if isinstance(raw_code, str | int) and not isinstance(raw_code, bool):
                code = str(raw_code)
        for key, value in _walk(payload):
            if key in ("quotaId", "quota_id") and isinstance(value, str):
                quota_ids.append(value)
            elif key in ("retryDelay", "retry_delay") and retry_delay is None:
                retry_delay = parse_duration(value)
    return ProviderErrorInfo(
        http_status=http_status,
        provider_status=status,
        provider_code=code,
        quota_ids=tuple(dict.fromkeys(quota_ids)),
        retry_after_seconds=header_retry_after if header_retry_after is not None else retry_delay,
    )
