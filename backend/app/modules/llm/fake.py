"""FakeProvider: a deterministic backend for tests. No network, no keys (rule 14).

- Replies are scripted per model (a string, or a function of the messages); otherwise a default.
- Replies stream word by word.
- `fail(model, error)` makes calls to that model raise a typed gateway error.
- Every call is recorded in `calls`, so tests can prove which models were (not) called.
- Embeddings are bag-of-words vectors (`word_vector`): texts sharing words are closer.
- Token counts are estimates: about 4 characters per token, plus 4 per message.
"""

import asyncio
import hashlib
import math
import re
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from typing import Any

from app.modules.llm.backend import (
    ChatMessages,
    EmbedInputType,
    EmbedResult,
    StreamItem,
    TextDelta,
    UsageInfo,
)
from app.modules.llm.errors import LLMError

Reply = str | Callable[[ChatMessages], str]


@dataclass
class FakeCall:
    kind: str  # "chat" or "embed"
    model: str
    messages: ChatMessages = field(default_factory=list)
    texts: list[str] = field(default_factory=list)
    max_tokens: int | None = None
    key_hint: str = ""  # last 4 characters of the key used, never the key
    input_type: str | None = None


_WORD = re.compile(r"[a-z0-9]+")


def word_vector(text: str, dimensions: int) -> list[float]:
    """A deterministic bag-of-words vector: each lowercase word adds 1 to the slot its hash
    picks, then the vector is scaled to length 1. Texts that share words get a higher cosine
    similarity, so retrieval tests can check ranking. An empty text gets a fixed unit vector,
    because pgvector can't compare a zero vector by cosine."""
    vector = [0.0] * dimensions
    for word in _WORD.findall(text.lower()):
        slot = int.from_bytes(hashlib.sha256(word.encode()).digest()[:8], "big") % dimensions
        vector[slot] += 1.0
    norm = math.sqrt(sum(v * v for v in vector))
    if norm == 0:
        vector[0] = 1.0
        return vector
    return [v / norm for v in vector]


def estimate_tokens(text: str) -> int:
    return math.ceil(len(text) / 4)


class FakeProvider:
    def __init__(
        self,
        replies: dict[str, Reply] | None = None,
        *,
        default_reply: str = "This is a fake reply.",
        delay: float = 0.0,
        embedding_dimensions: int = 1536,
    ) -> None:
        self.replies: dict[str, Reply] = dict(replies or {})
        self.default_reply = default_reply
        self.delay = delay
        self.embedding_dimensions = embedding_dimensions
        self.errors: dict[str, LLMError] = {}
        self.calls: list[FakeCall] = []

    def set_reply(self, model: str, reply: Reply) -> None:
        self.replies[model] = reply

    def fail(self, model: str, error: LLMError) -> None:
        self.errors[model] = error

    def calls_for(self, model: str) -> list[FakeCall]:
        return [c for c in self.calls if c.model == model]

    async def stream_chat(
        self, model: str, messages: ChatMessages, *, api_key: str, max_tokens: int | None
    ) -> AsyncIterator[StreamItem]:
        self.calls.append(
            FakeCall(
                "chat", model, messages=list(messages), max_tokens=max_tokens, key_hint=api_key[-4:]
            )
        )
        if model in self.errors:
            raise self.errors[model]
        reply = self.replies.get(model, self.default_reply)
        text = reply(messages) if callable(reply) else reply
        for piece in re.findall(r"\S+\s*", text) or [text]:
            if self.delay:
                await asyncio.sleep(self.delay)
            yield TextDelta(piece)
        yield UsageInfo(self.count_tokens(model, messages), estimate_tokens(text))

    async def embed(
        self,
        model: str,
        texts: list[str],
        *,
        api_key: str,
        dimensions: int | None = None,
        input_type: EmbedInputType | None = None,
    ) -> EmbedResult:
        self.calls.append(
            FakeCall(
                "embed", model, texts=list(texts), key_hint=api_key[-4:], input_type=input_type
            )
        )
        if model in self.errors:
            raise self.errors[model]
        size = dimensions or self.embedding_dimensions
        vectors = [word_vector(t, size) for t in texts]
        return EmbedResult(vectors=vectors, input_tokens=sum(estimate_tokens(t) for t in texts))

    def count_tokens(self, model: str, messages: ChatMessages) -> int:
        return sum(estimate_tokens(_content_text(m.get("content"))) + 4 for m in messages)


def _content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(str(p.get("text", "")) if isinstance(p, dict) else str(p) for p in content)
    return "" if content is None else str(content)
