"""Switch demo: measures the Phase 1 success metric with REAL models (docs/prd.md).

Not part of pytest. It makes real, paid API calls with the keys you saved in Mantle.

1. Creates a project and a conversation on model A.
2. Plays the scripted turns from switch_demo.yaml (5 decisions with reasons), streaming each
   reply, and runs the rolling summary after each reply exactly like the API does.
3. Switches to model B (never calls A during the switch) and prints the handoff note.
4. Asks the 5 questions, prints the answers and scores how many contain the expected facts.

Run from backend/ with the venv active, after `alembic upgrade head` and
`python -m app.db.seed`, with keys for both models saved (POST /api/v1/credentials):

    python scripts/switch_demo.py --model-a anthropic/claude-sonnet-5-5 --model-b openai/gpt-5.6
"""

import argparse
import asyncio
import sys
import textwrap
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.repositories import UserRepository  # noqa: E402
from app.db.session import SessionLocal, engine  # noqa: E402
from app.modules.conversations import service  # noqa: E402
from app.modules.conversations.summary import run_rolling_summary  # noqa: E402
from app.modules.llm.repository import ModelConfigRepository, UsageRecordRepository  # noqa: E402
from app.modules.llm.service import Gateway, LLMError, get_gateway  # noqa: E402
from app.modules.projects.service import create_project  # noqa: E402

DATA_FILE = Path(__file__).with_suffix(".yaml")
PASS_MARK = 4


@dataclass
class Score:
    question: str
    answer: str
    passed: bool
    missing: list[str]


def score(answer: str, expect_all: list[Any], expect_any: list[Any]) -> tuple[bool, list[str]]:
    text = answer.lower()
    missing = [str(w) for w in expect_all if str(w).lower() not in text]
    if expect_any and not any(str(w).lower() in text for w in expect_any):
        missing.append("one of: " + ", ".join(str(w) for w in expect_any))
    return not missing, missing


async def resolve_model(name: str) -> uuid.UUID:
    async with SessionLocal() as session:
        repo = ModelConfigRepository(session)
        model = await repo.get_by_litellm_model(name)
        if model is None:
            try:
                model = await repo.get(uuid.UUID(name))
            except ValueError:
                model = None
        if model is None:
            known = [m.litellm_model for m in await repo.list(kind="chat", limit=200)]
            raise SystemExit(f"Unknown model {name!r}. Known chat models: {', '.join(known)}")
        return model.id


async def ask(gateway: Gateway, user_id: uuid.UUID, conversation_id: uuid.UUID, text: str) -> str:
    async with SessionLocal() as session:
        prepared = await service.prepare_reply(session, gateway, user_id, conversation_id, text)
    parts: list[str] = []
    async for event in service.stream_reply(SessionLocal, gateway, user_id, prepared):
        if event.event == "delta":
            parts.append(event.data["text"])
        elif event.event == "error":
            raise SystemExit(f"Model error: {event.data['code']}: {event.data['message']}")
    # Same as the API: the rolling summary runs after each reply (if it's on and due).
    outcome = await run_rolling_summary(SessionLocal, gateway, user_id, conversation_id)
    if outcome in {"done", "failed"}:
        print(f"    [rolling summary: {outcome}]")
    return "".join(parts)


def show(label: str, text: str) -> None:
    print(f"\n{label}")
    print(textwrap.indent(textwrap.fill(text.strip(), 96), "    "))


async def run(model_a: str, model_b: str) -> int:
    data = yaml.safe_load(DATA_FILE.read_text(encoding="utf-8"))
    gateway = get_gateway()
    a_id, b_id = await resolve_model(model_a), await resolve_model(model_b)

    async with SessionLocal() as session:
        user = await UserRepository(session).get_default()
        if user is None:
            raise SystemExit("No default user. Run: python -m app.db.seed")
        stamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M")
        project = await create_project(
            session, user.id, f"{data['project']['name']} {stamp}", data["project"]["description"]
        )
        conversation = await service.create_conversation(
            session, user.id, project.id, a_id, title=f"Switch demo {stamp}"
        )
        await session.commit()
        user_id, conversation_id = user.id, conversation.id

    print(f"Project {project.id}, conversation {conversation_id}")
    print(f"Model A: {model_a}")
    for i, turn in enumerate(data["turns"], 1):
        show(f"[A] user turn {i}:", turn)
        show("[A] reply:", await ask(gateway, user_id, conversation_id, turn))

    async with SessionLocal() as session:
        result = await service.switch_model(session, gateway, user_id, conversation_id, b_id)
    print(f"\n=== Switched to model B: {model_b} ===")
    show("Handoff note:", result.handoff.note["text"])

    scores: list[Score] = []
    for i, item in enumerate(data["questions"], 1):
        answer = await ask(gateway, user_id, conversation_id, item["question"])
        passed, missing = score(answer, item.get("expect_all", []), item.get("expect_any", []))
        scores.append(Score(item["question"], answer, passed, missing))
        show(f"[B] question {i}: {item['question']}", answer)
        print("    -> PASS" if passed else f"    -> FAIL (missing {', '.join(missing)})")

    async with SessionLocal() as session:
        usage = await UsageRecordRepository(session, user_id).list(
            conversation_id=conversation_id, limit=500
        )
    lines: dict[str, int] = {}
    for u in usage:
        key = f"{u.purpose.value} ({u.trigger.value})"
        lines[key] = lines.get(key, 0) + 1
    print("\nUsage for this conversation: " + ", ".join(f"{k}: {v}" for k, v in lines.items()))

    passed = sum(s.passed for s in scores)
    verdict = "PASS" if passed >= PASS_MARK else "FAIL"
    print(f"\nScore: {passed}/{len(scores)} ({verdict}, needs {PASS_MARK})")
    return 0 if passed >= PASS_MARK else 1


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--model-a", required=True, help="LiteLLM model name or model id")
    parser.add_argument("--model-b", required=True, help="LiteLLM model name or model id")
    args = parser.parse_args()
    try:
        return await run(args.model_a, args.model_b)
    except LLMError as exc:
        print(f"Error: {exc.code}: {exc.message} {exc.details or ''}")
        return 2
    finally:
        await engine.dispose()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
