"""What indexing must never read or send: sensitive file names and secret-looking content.

Indexed text goes to a third-party embedding provider, so the rules are strict: a file that
merely looks like it holds a secret is skipped as a whole. False positives cost one file in the
index; a false negative leaks a key.

This file is named `secret_scan.py`, not `secrets.py`, so the indexer's own name rule
(`secrets*`) doesn't skip it when Mantle indexes itself.
"""

import re

import pathspec

from app.core.config import settings

# Gitignore syntax, matched against the path relative to the project root.
# `id_*` follows rule 48 literally: it also skips harmless files such as `id_utils.py`.
SENSITIVE_NAME_PATTERNS = (
    ".env",
    ".env.*",
    "*.env",
    "*.pem",
    "*.key",
    "*.pfx",
    "*.p12",
    "*.jks",
    "*.keystore",
    "*.kdbx",
    "id_*",
    "credentials*",
    "secrets*",
    ".netrc",
    ".npmrc",
    ".pypirc",
    ".htpasswd",
)

# Content patterns. Each is specific enough to be rare in ordinary code.
_SECRET_PATTERNS = re.compile(
    "|".join(
        (
            r"-----BEGIN (?:[A-Z]+ )*PRIVATE KEY(?: BLOCK)?-----",  # PEM, OpenSSH, PGP
            r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b",  # AWS access key id
            r"(?i:aws_secret_access_key)\s*[=:]\s*['\"]?[A-Za-z0-9/+=]{40}",
            r"\bsk-(?:proj-|ant-)?[A-Za-z0-9_-]{20,}",  # OpenAI, Anthropic
            r"\bAIza[0-9A-Za-z_-]{35}\b",  # Google API key
            r"\bgh[pousr]_[A-Za-z0-9]{36,}\b",  # GitHub tokens
            r"\bgithub_pat_[A-Za-z0-9_]{22,}",
            r"\bxox[abprs]-[A-Za-z0-9-]{10,}",  # Slack
            r"\b[rs]k_live_[A-Za-z0-9]{20,}",  # Stripe live keys
        )
    )
)


def sensitive_spec() -> pathspec.GitIgnoreSpec:
    """The built-in list plus `INDEX_SENSITIVE_PATTERNS`."""
    return pathspec.GitIgnoreSpec.from_lines(
        [*SENSITIVE_NAME_PATTERNS, *settings.index_sensitive_patterns]
    )


def looks_like_secret(text: str) -> bool:
    """True when `text` contains something shaped like a private key or an API key."""
    return _SECRET_PATTERNS.search(text) is not None
