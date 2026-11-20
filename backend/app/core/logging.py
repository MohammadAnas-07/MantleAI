"""Logging setup, with a filter that masks what must never reach a log (security.md #6).

The filter is the second line of defence. Code logs only types, codes, ids, counts and timings;
the filter catches what slips through anyway: key shapes, Authorization headers, SQL statement
parameters (they can be message text, memory or code), Fernet tokens, and the same inside a
formatted traceback. It is attached to the root handlers and to uvicorn's own handlers, which
don't pass through the root logger.
"""

import logging
import re

_SECRET_PATTERNS = [
    re.compile(r"\bsk-[A-Za-z0-9_\-]{8,}"),  # OpenAI, Anthropic (sk-ant-...)
    re.compile(r"\bAIza[A-Za-z0-9_\-]{20,}"),  # Google
    re.compile(r"\bpa-[A-Za-z0-9_\-]{20,}"),  # Voyage
    re.compile(r"\bgAAAAA[A-Za-z0-9_\-]{20,}={0,2}"),  # a Fernet token: an encrypted provider key
    # SQLAlchemy appends the bound values to its error text (hidden at the source by
    # hide_parameters=True; masked here too).
    # Printed on one line; masked to its end, because a value may itself contain "]".
    re.compile(r"\[parameters: [^\n]*"),
]
_ASSIGNMENTS = re.compile(
    r"(?i)\b(authorization|x-api-key|api[_-]?key|master_encryption_key|password)"
    r"(\"?'?\s*[:=]\s*\"?'?)(bearer\s+)?[^\s\"',]+"
)
MASK = "[REDACTED]"
UVICORN_LOGGERS = ("uvicorn", "uvicorn.error", "uvicorn.access")


def mask_secrets(text: str) -> str:
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub(MASK, text)
    return _ASSIGNMENTS.sub(lambda m: f"{m.group(1)}{m.group(2)}{MASK}", text)


class SecretMaskingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        masked = mask_secrets(message)
        if masked != message:
            record.msg, record.args = masked, None
        if record.exc_info:
            # Format the traceback now and mask it; the formatter then prints this text.
            record.exc_text = mask_secrets(logging.Formatter().formatException(record.exc_info))
            record.exc_info = None
        elif record.exc_text:
            record.exc_text = mask_secrets(record.exc_text)
        return True


def _add_filter(logger: logging.Logger) -> None:
    for handler in logger.handlers:
        if not any(isinstance(f, SecretMaskingFilter) for f in handler.filters):
            handler.addFilter(SecretMaskingFilter())


def setup_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=level.upper(),
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    )
    _add_filter(logging.getLogger())
    for name in UVICORN_LOGGERS:
        _add_filter(logging.getLogger(name))
