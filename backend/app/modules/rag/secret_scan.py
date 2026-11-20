"""What indexing must never read or send: sensitive file names and secret-looking content.

Indexed text goes to a third-party embedding provider, so the rules are strict: a file that
merely looks like it holds a secret is skipped as a whole. False positives cost one file in the
index; a false negative leaks a key. Three kinds of content rule:

1. Known token formats (private keys, cloud and provider keys, JWTs, webhooks).
2. Connection strings with a password (postgres, mysql, mongodb, redis, amqp, ...).
3. Assignments: a secret-looking name (`password`, `api_key`, `clientSecret`, `DB_TOKEN`, ...)
   given a literal value. Code files count only quoted values; config files (YAML, TOML, INI,
   JSON, .env-style, terraform, docker-compose) also count bare values. Placeholders such as
   `your-key-here`, `${VAR}` or `changeme` don't count. A looser name ending in `key` counts only
   with a long, high-entropy value that isn't a hex digest or a UUID.

Pattern matching can't find every secret; docs/security.md lists what isn't covered. The result
is only a yes or no: what matched is never returned, stored or logged.

This file is named `secret_scan.py`, not `secrets.py`, so the indexer's own name rule
(`secrets*`) doesn't skip it when Mantle indexes itself.
"""

import math
import re
from collections import Counter
from pathlib import PurePosixPath

import pathspec

from app.core.config import settings

# Bump when the content rules change: every indexed file is then read and checked again on the
# next index run, even if it didn't change (documents.scan_version).
RULES_VERSION = 2

# Gitignore syntax, matched against the path relative to the project root, before any content
# is read. `id_*` follows rule 48 literally: it also skips harmless files such as `id_utils.py`.
SENSITIVE_NAME_PATTERNS = (
    # environment files
    ".env", ".env.*", "*.env", ".envrc",
    # keys and certificates
    "*.pem", "*.key", "*.crt", "*.cer", "*.der", "*.p7b", "*.p7c", "*.pfx", "*.p12", "*.jks",
    "*.keystore", "*.kdbx", "*.ppk", "*.gpg", "id_*",
    # credential files
    "credentials*", "*credentials.json", "service-account*.json", "service_account*.json",
    "serviceaccount*.json", "secrets*", ".netrc", ".npmrc", ".pypirc", ".htpasswd",
    ".git-credentials", ".pgpass", ".my.cnf", "local.settings.json", "wp-config.php",
    # cloud and cluster config
    "**/.aws/config", "**/.docker/config.json", ".dockercfg", "kubeconfig", "*.kubeconfig",
    "**/.kube/config", "*.ovpn",
    # terraform variables and state
    "*.tfvars", "*.tfvars.json", "*.tfstate", "*.tfstate.*",
)  # fmt: skip

# 1. Known formats. Each is specific enough to be rare in ordinary code.
_FORMATS = re.compile(
    "|".join(
        (
            r"-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY(?: BLOCK)?-----",  # PEM, OpenSSH, PGP
            r"PuTTY-User-Key-File-\d",
            r"\b(?:AKIA|ASIA|AGPA|AIDA|AROA|ANPA|ANVA|AIPA)[0-9A-Z]{16}\b",  # AWS key ids
            r"\bsk-(?:proj-|ant-|svcacct-|admin-)?[A-Za-z0-9_-]{20,}",  # OpenAI, Anthropic
            r"\bAIza[0-9A-Za-z_-]{35}\b",  # Google API key
            r"\bGOCSPX-[A-Za-z0-9_-]{24,}",  # Google OAuth client secret
            r"\bgh[pousr]_[A-Za-z0-9]{36,}\b",  # GitHub tokens
            r"\bgithub_pat_[A-Za-z0-9_]{22,}",
            r"\bglpat-[A-Za-z0-9_-]{20,}",  # GitLab
            r"\bxox[abposr]-[A-Za-z0-9-]{10,}",  # Slack tokens
            r"hooks\.slack\.com/services/T[A-Z0-9]+/B[A-Z0-9]+/[A-Za-z0-9]{20,}",
            r"\b[rs]k_(?:live|test)_[A-Za-z0-9]{20,}",  # Stripe secret and restricted keys
            r"\bwhsec_[A-Za-z0-9]{24,}",  # Stripe webhook secret
            r"\bhf_[A-Za-z]{30,}",  # Hugging Face
            r"\bnpm_[A-Za-z0-9]{36}\b",
            r"\bSG\.[A-Za-z0-9_-]{16,}\.[A-Za-z0-9_-]{16,}",  # SendGrid
            r"\bpypi-AgEIcHlwaS5vcmc[A-Za-z0-9_-]{40,}",
            r"AccountKey=[A-Za-z0-9+/]{40,}={0,2}",  # Azure storage
            r"\beyJ[A-Za-z0-9_-]{8,}\.eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}",  # signed JWT
        )
    )
)

# 2. Connection strings with a password.
_DB_URL = re.compile(
    r"\b(?:postgres(?:ql)?|mysql|mariadb|mongodb(?:\+srv)?|rediss?|amqps?|mssql|sqlserver|oracle)"
    r"(?:\+[a-z0-9]+)?://(?P<user>[^\s:/@'\"`]*):(?P<pw>[^\s@/'\"`]+)@(?P<host>[^\s:/'\"`]*)",
    re.IGNORECASE,
)
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "[::1]", "::1"}

# 3. Assignments: `name = value`, `name: value`, `"name": "value"`.
_ASSIGNMENT = re.compile(
    r"(?P<key>[A-Za-z_][A-Za-z0-9_.-]*)[\"']?[ \t]*(?:=|:(?!:))[ \t]*"
    r"(?:\"(?P<dq>[^\"\n]*)\"|'(?P<sq>[^'\n]*)'|(?P<bare>[^\s\"'#;,]+))"
)
_SECRET_WORDS = {"password", "passwd", "pwd", "passphrase", "secret", "token", "apikey",
                 "credential", "credentials"}  # fmt: skip
_KEY_PREFIXES = {"api", "access", "secret", "private", "client", "auth", "encryption",
                 "signing", "master", "account", "app", "license", "service", "subscription",
                 "sas"}  # fmt: skip
_PASSWORD_WORDS = {"password", "passwd", "pwd", "passphrase"}

_CONFIG_SUFFIXES = {".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf", ".env", ".properties",
                    ".tf", ".hcl", ".json", ".jsonc", ".xml"}  # fmt: skip

_PLACEHOLDER_PARTS = ("your", "example", "sample", "dummy", "fake", "placeholder", "changeme",
                      "change_me", "change-me", "replace", "redacted", "insert", "xxx", "***",
                      "...", "{{", "${", "%(")  # fmt: skip
_PLACEHOLDER_VALUES = {"password", "passwd", "secret", "token", "string", "str", "none", "null",
                       "nil", "true", "false", "undefined", "required", "optional", "hidden",
                       "masked", "bearer", "basic", "pass", "user", "username"}  # fmt: skip
_REFERENCE_STARTS = ("$", "<", "{", "[", "(", "%", "!", "&", "*", "@", "os.", "process.",
                     "env.", "settings.", "config.", "self.", "getenv", "import.meta")  # fmt: skip

_HEX = re.compile(r"^[0-9a-fA-F]+$")
_UUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
_CAMEL = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")


def sensitive_spec() -> pathspec.GitIgnoreSpec:
    """The built-in list plus `INDEX_SENSITIVE_PATTERNS`."""
    return pathspec.GitIgnoreSpec.from_lines(
        [*SENSITIVE_NAME_PATTERNS, *settings.index_sensitive_patterns]
    )


def _is_config(name: str) -> bool:
    lower = name.lower()
    return (
        PurePosixPath(lower).suffix in _CONFIG_SUFFIXES
        or lower.startswith((".env", "docker-compose", "compose.", "dockerfile"))
        or lower.endswith(".env")
    )


def _placeholder(value: str) -> bool:
    lower = value.strip().lower()
    return (
        not lower
        or lower in _PLACEHOLDER_VALUES
        or lower.startswith(_REFERENCE_STARTS)
        or any(part in lower for part in _PLACEHOLDER_PARTS)
        or len(set(lower)) <= 2  # "xxxxxxxx", "********"
    )


def _entropy(value: str) -> float:
    counts = Counter(value)
    return -sum(n / len(value) * math.log2(n / len(value)) for n in counts.values())


def _key_kind(key: str) -> str | None:
    """ "strict" for a name that says it holds a secret, "loose" for one ending in `key`."""
    words = [w for w in re.split(r"[_.\-]+", _CAMEL.sub("_", key).lower()) if w]
    while words and words[-1].isdigit():
        words.pop()
    if not words:
        return None
    last = words[-1]
    if last in _SECRET_WORDS:
        return "strict"
    if last == "key":
        return "strict" if len(words) > 1 and words[-2] in _KEY_PREFIXES else "loose"
    return None


def _secret_value(kind: str, key: str, value: str) -> bool:
    if _placeholder(value) or any(c.isspace() for c in value):
        return False
    if kind == "loose":
        return (
            len(value) >= 20
            and not _HEX.match(value)
            and not _UUID.match(value)
            and _entropy(value) >= 3.5
        )
    words = set(re.split(r"[_.\-]+", _CAMEL.sub("_", key).lower()))
    if words & _PASSWORD_WORDS:
        return len(value) >= 6
    mixed = any(c.isdigit() for c in value) or (value.lower() != value and value.upper() != value)
    return len(value) >= 8 and (mixed or len(value) >= 16)


def _db_url_secret(match: re.Match[str]) -> bool:
    user, password, host = match.group("user"), match.group("pw"), match.group("host").lower()
    if _placeholder(password):
        return False
    # A local default such as postgres:postgres@localhost is not worth hiding the file for.
    return not (host in _LOCAL_HOSTS and password == user)


def looks_like_secret(text: str, name: str = "") -> bool:
    """True when `text` (the content of file `name`) contains something shaped like a secret."""
    if _FORMATS.search(text):
        return True
    if any(_db_url_secret(m) for m in _DB_URL.finditer(text)):
        return True
    return _has_secret_assignment(text, bare_counts=_is_config(name), nested=True)


def _has_secret_assignment(text: str, *, bare_counts: bool, nested: bool) -> bool:
    for match in _ASSIGNMENT.finditer(text):
        quoted = match.group("dq") if match.group("dq") is not None else match.group("sq")
        # A quoted "Server=...;Password=...;" string: look inside it too, where bare values
        # count (one level deep).
        if nested and quoted and "=" in quoted and ";" in quoted:
            if _has_secret_assignment(quoted, bare_counts=True, nested=False):
                return True
        kind = _key_kind(match.group("key"))
        if kind is None:
            continue
        value = quoted
        if value is None:
            if not bare_counts:
                continue
            value = match.group("bare")
        if value is not None and _secret_value(kind, match.group("key"), value):
            return True
    return False
