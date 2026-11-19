"""Shared setup for gap finder and agent tests: a project with memory, fake models with prices,
and a FakeProvider whose replies are scripted per agent. No keys, no network."""

import json
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.llm.fake import FakeProvider
from app.modules.llm.gateway import Gateway
from app.modules.llm.repository import ModelConfigRepository, ProviderCredentialRepository
from app.modules.llm.service import ChatMessages
from app.modules.projects.repository import MemoryItemRepository, ProjectRepository
from tests.graph import make_user

AGENT_MARKERS = {
    "gap_finder": "You review the state of one software project",
    "planner": "You are the Planner",
    "reviewer": "You are the Reviewer",
}


def which_agent(messages: ChatMessages) -> str:
    system = str(messages[0]["content"])
    for agent, marker in AGENT_MARKERS.items():
        if system.startswith(marker):
            return agent
    raise AssertionError("unknown prompt")


@dataclass
class Script:
    """Replies per agent, used in order; the last one repeats. Every prompt is kept so tests
    can check what the model saw."""

    replies: dict[str, list[str]] = field(default_factory=lambda: defaultdict(list))
    prompts: list[tuple[str, ChatMessages]] = field(default_factory=list)
    used: dict[str, int] = field(default_factory=lambda: defaultdict(int))

    def say(self, agent: str, *replies: str | dict[str, Any]) -> None:
        self.replies[agent] = [r if isinstance(r, str) else json.dumps(r) for r in replies]
        self.used[agent] = 0

    def __call__(self, messages: ChatMessages) -> str:
        agent = which_agent(messages)
        self.prompts.append((agent, list(messages)))
        queue = self.replies[agent]
        assert queue, f"no scripted reply for {agent}"
        reply = queue[min(self.used[agent], len(queue) - 1)]
        self.used[agent] += 1
        return reply

    def calls(self, agent: str) -> int:
        return sum(1 for a, _ in self.prompts if a == agent)


@dataclass
class AgentWorld:
    user_id: uuid.UUID
    project_id: uuid.UUID
    model_id: uuid.UUID
    model_name: str
    big_model_id: uuid.UUID
    tiny_model_id: uuid.UUID
    fake: FakeProvider
    gateway: Gateway
    script: Script
    memory: dict[str, uuid.UUID]  # name -> memory item id


async def add_model(
    session: AsyncSession, user_id: uuid.UUID, name: str, provider: str, window: int,
    max_out: int, price: str = "1.00",
) -> tuple[uuid.UUID, str]:  # fmt: skip
    litellm = f"fake/{name}-{uuid.uuid4().hex[:6]}"
    row = await ModelConfigRepository(session).add(
        provider=provider, litellm_model=litellm, display_name=f"Fake {name}", kind="chat",
        context_window=window, max_output_tokens=max_out, supports_tools=False,
        input_cost_per_mtok=Decimal(price), output_cost_per_mtok=Decimal(price) * 2,
    )  # fmt: skip
    return row.id, litellm


async def make_agent_world(session: AsyncSession, name: str = "Agents") -> AgentWorld:
    user_id = await make_user(session, name)
    for provider in ("openai", "google"):
        await ProviderCredentialRepository(session, user_id).add_key(
            provider=provider, api_key=f"sk-test-{provider}-0000"
        )
    model_id, model_name = await add_model(session, user_id, "agent", "openai", 100_000, 4_000)
    big_id, _ = await add_model(session, user_id, "big", "google", 1_000_000, 4_000)
    tiny_id, _ = await add_model(session, user_id, "tiny", "openai", 1_200, 1_000)
    project = await ProjectRepository(session, user_id).add(name="Shop", description="A shop")
    items = MemoryItemRepository(session, user_id)
    memory: dict[str, uuid.UUID] = {}
    for key, values in {
        "req_login": {"kind": "requirement", "title": "Users can log in", "status": "approved",
                      "priority": "must", "body": "Email and password."},
        "req_draft": {"kind": "requirement", "title": "Export orders", "status": "draft",
                      "body": "CSV export of orders."},
        "dec_db": {"kind": "decision", "title": "Use PostgreSQL", "status": "accepted",
                   "body": "One database.", "why": "pgvector"},
        "task_schema": {"kind": "task", "title": "Create the user table", "status": "todo",
                        "priority": "high", "body": ""},
    }.items():  # fmt: skip
        row = await items.add(project_id=project.id, **values)
        memory[key] = row.id
    script = Script()
    fake = FakeProvider()
    fake.set_reply(model_name, script)
    return AgentWorld(
        user_id=user_id, project_id=project.id, model_id=model_id, model_name=model_name,
        big_model_id=big_id, tiny_model_id=tiny_id, fake=fake, gateway=Gateway(fake),
        script=script, memory=memory,
    )  # fmt: skip


def short(item_id: uuid.UUID) -> str:
    return item_id.hex[:8]


def gap_report(refs: list[str] | None = None) -> dict[str, Any]:
    item = {"title": "No password reset", "explanation": "Users who forget a password are stuck.",
            "severity": "high", "refers_to": refs or []}  # fmt: skip
    return {"missing_steps": [item], "risks": [], "technical_debt": [], "scalability_concerns": []}


def plan(tasks: list[dict[str, Any]] | None = None, decisions: list[dict[str, Any]] | None = None,
         ) -> dict[str, Any]:  # fmt: skip
    if tasks is None:
        tasks = [
            {"title": "Login form", "description": "Email and password fields.",
             "priority": "high", "acceptance_criteria": ["Shows an error on a wrong password"],
             "depends_on": []},
            {"title": "Session cookie", "description": "Keep users logged in.",
             "priority": "medium", "acceptance_criteria": ["Cookie is HttpOnly"],
             "depends_on": [0]},
            {"title": "Logout button", "description": "Ends the session.", "priority": "low",
             "acceptance_criteria": [], "depends_on": [1]},
        ]  # fmt: skip
    if decisions is None:
        decisions = [{"title": "Use argon2 for passwords", "what": "Hash with argon2id.",
                      "why": "Slow to brute force.", "alternatives": "bcrypt"}]  # fmt: skip
    return {"tasks": tasks, "decisions": decisions, "assumptions": ["One user role"],
            "risks": ["Brute force"], "open_questions": ["Do we need 2FA?"]}  # fmt: skip


def review(verdict: str = "approve", refs: list[str] | None = None) -> dict[str, Any]:
    return {
        "findings": [{"severity": "medium", "refers_to": refs or ["task:0"],
                      "explanation": "No rate limit on login.", "suggestion": "Add one."}],
        "verdict": verdict,
    }  # fmt: skip
