"""What the gap finder, Planner and Reviewer see, and whether it fits the model.

Every piece of project data goes into the user message inside its own tag (`<project>`,
`<stage>`, `<project_memory>`, `<requirement>`, `<plan>`, `<retrieved_context>`), with our tags
and chat-template markers defanged (app.core.prompt_data). The system message is the versioned
prompt file and says the data is not instructions.

Budget per step: the model's context window minus the output reserve and a safety margin, and
never more than AGENT_MAX_INPUT_TOKENS. Memory uses at most AGENT_MEMORY_MAX_SHARE of it, picked
with the same rules as pinned items. Too big even then: ContextTooLong with suggested models.
"""

import json
import math
import uuid
from collections import Counter
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.prompt_data import defang, defang_attr
from app.modules.llm.service import (
    ChatMessages,
    ContextTooLong,
    Gateway,
    ModelInfo,
    count_tokens,
    suggest_models,
)
from app.modules.projects.service import MemoryRef, ProjectInfo, pinned_block, pinned_selection
from app.modules.rag.service import RetrievedBlock
from app.modules.workflow.outputs import Plan
from app.modules.workflow.state import StageView

TAGS = (
    "project", "stage", "project_memory", "pinned_items", "requirement", "plan",
    "retrieved_context", "source",
)  # fmt: skip


def attr(value: str) -> str:
    """A path, symbol or language for a quoted attribute: defanged and quote-escaped."""
    return defang_attr(value, TAGS)


def safe(text: str) -> str:
    """Defang our tags and chat-template markers inside untrusted text."""
    return defang(text, TAGS)


def output_reserve(model: ModelInfo) -> int:
    """Tokens kept free for the reply: AGENT_MAX_OUTPUT_TOKENS, or less if the model allows less."""
    limit = settings.agent_max_output_tokens
    return min(limit, model.max_output_tokens) if model.max_output_tokens else limit


def input_budget(model: ModelInfo) -> int:
    """Tokens the prompt may use for this model."""
    margin = math.ceil(model.context_window * settings.context_safety_margin)
    budget = model.context_window - output_reserve(model) - margin
    return max(min(budget, settings.agent_max_input_tokens), 0)


@dataclass
class AgentInputs:
    """Data for one run, gathered once and reused by every step."""

    project: ProjectInfo
    stage: StageView
    memory: list[MemoryRef]
    memory_text: str = ""
    memory_dropped: int = 0
    requirement: str | None = None
    code: list[RetrievedBlock] = field(default_factory=list)


def project_text(project: ProjectInfo, memory: list[MemoryRef]) -> str:
    """The project's name, description and memory counts."""
    counts = Counter(f"{m.kind}:{m.status}" for m in memory)
    summary = ", ".join(f"{n} {key}" for key, n in sorted(counts.items())) or "no memory items"
    lines = [f"name: {project.name}"]
    if project.description:
        lines.append(f"description: {project.description.strip()[:500]}")
    lines.append(f"memory: {summary}")
    return "<project>\n" + safe("\n".join(lines)) + "\n</project>"


def stage_text(stage: StageView) -> str:
    """The stage goal, its checklist with ticks, and the artifact rules with counts."""
    d = stage.definition
    lines = [f"id: {d.id}", f"title: {d.title}", f"goal: {d.goal}", "checklist:"]
    for item in d.checklist:
        mark = "x" if item.id in stage.ticked else " "
        need = "required" if item.required else "optional"
        lines.append(f"- [{mark}] {item.text} ({need})")
    if stage.artifacts:
        lines.append("expected in memory:")
        for rule, have in stage.artifacts:
            lines.append(f"- {rule.text} (have {have})")
    return "<stage>\n" + safe("\n".join(lines)) + "\n</stage>"


def requirement_text(text: str) -> str:
    """The requirement the Planner works on."""
    return "<requirement>\n" + safe(text.strip()) + "\n</requirement>"


def plan_text(plan: Plan) -> str:
    """The draft plan for the Reviewer, with items numbered as task:N and decision:N."""
    data = plan.model_dump(exclude={"tasks": {"__all__": {"possible_duplicate_of"}}})
    numbered = {
        "tasks": {f"task:{i}": t for i, t in enumerate(data["tasks"])},
        "decisions": {f"decision:{i}": d for i, d in enumerate(data["decisions"])},
        "assumptions": data["assumptions"],
        "risks": data["risks"],
        "open_questions": data["open_questions"],
    }
    return "<plan>\n" + safe(json.dumps(numbered, indent=1, ensure_ascii=False)) + "\n</plan>"


def code_text(blocks: list[RetrievedBlock]) -> str:
    """Retrieved code blocks as `<source>` data, or nothing."""
    if not blocks:
        return ""
    parts = []
    for b in blocks:
        attrs = f'path="{attr(b.path)}" lines="{b.start_line}-{b.end_line}"'
        if b.symbol:
            attrs += f' symbol="{attr(b.symbol)}"'
        if b.language:
            attrs += f' language="{attr(b.language)}"'
        parts.append(f"<source {attrs}>\n{safe(b.text)}\n</source>")
    return "<retrieved_context>\n" + "\n".join(parts) + "\n</retrieved_context>"


def messages(system_text: str, sections: list[str]) -> ChatMessages:
    """The system prompt, then one user message with every data section."""
    body = "\n\n".join(s for s in sections if s)
    body += "\n\nAnswer now with the JSON object only."
    return [
        {"role": "system", "content": system_text.strip()},
        {"role": "user", "content": body},
    ]


async def load_memory(
    session: AsyncSession,
    gateway: Gateway,
    user_id: uuid.UUID,
    project_id: uuid.UUID,
    model: ModelInfo,
    inputs: AgentInputs,
) -> None:
    """Fill `memory_text` within the memory share of the budget, pinned-item rules."""

    def count(text: str) -> int:
        return count_tokens(gateway, model, [{"role": "user", "content": text}])

    selection = await pinned_selection(
        session, user_id, project_id,
        max_tokens=int(input_budget(model) * settings.agent_memory_max_share), count=count,
    )  # fmt: skip
    block = pinned_block(selection.items)
    lines = block.splitlines()[1:-1] if block else []
    text = "\n".join(safe(line) for line in lines) or "(no memory items)"
    inputs.memory_text = "<project_memory>\n" + text + "\n</project_memory>"
    inputs.memory_dropped = len(selection.dropped)


async def check_fits(
    session: AsyncSession,
    gateway: Gateway,
    user_id: uuid.UUID,
    model: ModelInfo,
    prompt: ChatMessages,
) -> int:
    """Prompt tokens, or ContextTooLong (with suggested models) when over the budget."""
    tokens = count_tokens(gateway, model, prompt)
    budget = input_budget(model)
    if tokens > budget:
        error = ContextTooLong(
            f"The prompt needs about {tokens} tokens; {model.display_name} allows {budget} here. "
            "Pick a model with a bigger context window, or trim project memory.",
            details={"model": model.litellm_model, "tokens": tokens, "budget": budget},
        )
        error.details["suggested_models"] = await suggest_models(
            session, user_id, model, "context_too_long"
        )
        raise error
    return tokens
