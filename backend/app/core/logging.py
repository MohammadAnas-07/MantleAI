"""Logging setup, with a filter that masks anything that looks like a key (security.md #6).

The filter is a safety net. Code must still never log keys, prompts, replies or file contents.
"""

import logging
import re

# Provider key shapes and Authorization headers.
_SECRET_PATTERNS = [
    re.compile(r"\bsk-[A-Za-z0-9_\-]{8,}"),  # OpenAI, Anthropic (sk-ant-...)
    re.compile(r"\bAIza[A-Za-z0-9_\-]{20,}"),  # Google
    re.compile(r"\bpa-[A-Za-z0-9_\-]{20,}"),  # Voyage
    re.compile(
        r"(?i)\b(authorization|x-api-key|api[_-]?key)(\"?\s*[:=]\s*\"?)(bearer\s+)?[^\s\"',]+"
    ),
]
MASK = "[REDACTED]"


def mask_secrets(text: str) -> str:
    for pattern in _SECRET_PATTERNS[:-1]:
        text = pattern.sub(MASK, text)
    return _SECRET_PATTERNS[-1].sub(lambda m: f"{m.group(1)}{m.group(2)}{MASK}", text)


class SecretMaskingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        masked = mask_secrets(message)
        if masked != message:
            record.msg, record.args = masked, None
        return True


def setup_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=level.upper(),
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    )
    for handler in logging.getLogger().handlers:
        if not any(isinstance(f, SecretMaskingFilter) for f in handler.filters):
            handler.addFilter(SecretMaskingFilter())
