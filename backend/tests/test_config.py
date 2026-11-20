"""Configuration in one place (rule 5, audit A-019): only app/core/config.py touches the
process environment, and every setting is listed in backend/.env.example."""

import re
from pathlib import Path

from app.core.config import Settings

BACKEND = Path(__file__).resolve().parents[1]
ENV_ACCESS = re.compile(r"\bos\.(environ|getenv|putenv)\b|\bgetenv\(")


def test_only_the_config_module_touches_the_environment() -> None:
    found = []
    for path in sorted((BACKEND / "app").rglob("*.py")):
        if path == BACKEND / "app" / "core" / "config.py":
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if ENV_ACCESS.search(line):
                found.append(f"{path.relative_to(BACKEND)}:{number}")
    assert found == []


def test_every_setting_is_in_env_example() -> None:
    example = (BACKEND / ".env.example").read_text(encoding="utf-8")
    listed = set(re.findall(r"^#?\s*([A-Z][A-Z0-9_]+)=", example, re.MULTILINE))
    missing = sorted(name.upper() for name in Settings.model_fields if name.upper() not in listed)
    assert missing == []
