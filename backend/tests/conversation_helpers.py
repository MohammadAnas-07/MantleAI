"""Shared setup for conversation tests: fake models of different sizes, keys, a project and a
conversation, and a deterministic fake summarizer."""

import re
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.conversations.models import MessageStatus
from app.modules.conversations.repository import ConversationRepository, MessageRepository
from app.modules.llm.fake import FakeProvider
from app.modules.llm.repository import ModelConfigRepository, ProviderCredentialRepository
from app.modules.llm.service import ChatMessages
from app.modules.projects.repository import ProjectRepository
from tests.graph import make_user


@dataclass
class World:
    user_id: uuid.UUID
    project_id: uuid.UUID
    conversation_id: uuid.UUID
    # name -> (model id, litellm name)
    models: dict[str, tuple[uuid.UUID, str]]

    def id(self, name: str) -> uuid.UUID:
        return self.models[name][0]

    def litellm(self, name: str) -> str:
        return self.models[name][1]


# Three fake chat models with very different context windows, from three providers.
FAKE_MODELS = {
    "small": ("openai", 8_000, False),
    "medium": ("anthropic", 32_000, True),
    "large": ("google", 200_000, False),
}


async def make_world(session: AsyncSession, name: str = "Dev", start: str = "small") -> World:
    user_id = await make_user(session, name)
    models: dict[str, tuple[uuid.UUID, str]] = {}
    for key, (provider, window, tools) in FAKE_MODELS.items():
        litellm = f"fake/{key}-{uuid.uuid4().hex[:6]}"
        row = await ModelConfigRepository(session).add(
            provider=provider, litellm_model=litellm, display_name=f"Fake {key}", kind="chat",
            context_window=window, max_output_tokens=1_000, supports_tools=tools,
        )  # fmt: skip
        models[key] = (row.id, litellm)
        await ProviderCredentialRepository(session, user_id).add_key(
            provider=provider, api_key=f"sk-test-{provider}-{key}-0000"
        )
    project = await ProjectRepository(session, user_id).add(name="Demo project")
    conversation = await ConversationRepository(session, user_id).add(
        project_id=project.id, title="Chat", current_model_id=models[start][0]
    )
    return World(user_id, project.id, conversation.id, models)


async def add_messages(
    session: AsyncSession, world: World, texts: list[tuple[str, str]], tokens_each: int = 100
) -> None:
    """Append (role, text) messages with a fixed token_count each."""
    repo = MessageRepository(session, world.user_id)
    for role, body in texts:
        await repo.add(
            conversation_id=world.conversation_id,
            sequence=await repo.next_sequence(world.conversation_id),
            role=role,
            content=[{"type": "text", "text": body}],
            status=MessageStatus.COMPLETE,
            token_count=tokens_each,
        )


def turns(start: int, count: int) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for i in range(start, start + count):
        out += [("user", f"question {i}"), ("assistant", f"answer {i}")]
    return out


def fake_summarizer(messages: ChatMessages) -> str:
    """Deterministic 'summary': the previous summary plus the message numbers it was given."""
    prompt = str(messages[-1]["content"])
    previous = re.search(r"<previous_summary>\n(.*?)\n</previous_summary>", prompt, re.S)
    new = re.search(r"<new_messages>\n(.*?)\n</new_messages>", prompt, re.S)
    prev = previous.group(1) if previous else ""
    seqs = re.findall(r"\[#(\d+) ", new.group(1) if new else "")
    prefix = "" if prev == "(none yet)" else prev + " | "
    return f"{prefix}covered {','.join(seqs)}"


def session_factory(session: AsyncSession):  # noqa: ANN201
    """A session factory that hands out the test session (its transaction is rolled back)."""

    @asynccontextmanager
    async def factory() -> AsyncIterator[AsyncSession]:
        yield session

    return factory


def summarizer_provider(*model_names: str) -> FakeProvider:
    fake = FakeProvider(default_reply="Fake answer.")
    for name in model_names:
        fake.set_reply(name, fake_summarizer)
    return fake
