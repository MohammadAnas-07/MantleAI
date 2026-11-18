"""Versioned prompt files. Change a prompt by adding `<name>_v2.txt` and bumping the version
here, so old behaviour stays reproducible."""

from functools import cache
from pathlib import Path

PROMPTS_DIR = Path(__file__).resolve().parent

SYSTEM_PROMPT = "system_v2"
SUMMARY_PROMPT = "summary_v1"


@cache
def load_prompt(name: str) -> str:
    return (PROMPTS_DIR / f"{name}.txt").read_text(encoding="utf-8")
