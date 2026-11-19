"""Versioned prompt files. Change a prompt by adding `<name>_v2.txt` and pointing the
constant at it, so a stored run still names the exact prompt it used."""

from functools import cache
from pathlib import Path

PROMPTS_DIR = Path(__file__).resolve().parent

GAP_FINDER_PROMPT = "gap_finder_v1"
PLANNER_PROMPT = "planner_v1"
REVIEWER_PROMPT = "reviewer_v1"


@cache
def load_prompt(name: str) -> str:
    return (PROMPTS_DIR / f"{name}.txt").read_text(encoding="utf-8")
