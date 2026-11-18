"""The interface every LLM backend implements: LiteLLM for real calls, FakeProvider for tests.

Messages are OpenAI-style dicts (`{"role": ..., "content": "..."}`). The gateway handles keys,
usage records and logging; a backend only talks to the provider.
"""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, Protocol

ChatMessages = list[dict[str, Any]]


@dataclass(frozen=True)
class TextDelta:
    text: str


@dataclass(frozen=True)
class UsageInfo:
    input_tokens: int
    output_tokens: int


StreamItem = TextDelta | UsageInfo


@dataclass(frozen=True)
class EmbedResult:
    vectors: list[list[float]]
    input_tokens: int


class Backend(Protocol):
    def stream_chat(
        self, model: str, messages: ChatMessages, *, api_key: str, max_tokens: int | None
    ) -> AsyncIterator[StreamItem]:
        """Yield text deltas, then at most one UsageInfo. Raises only LLMError subclasses."""
        ...

    async def embed(self, model: str, texts: list[str], *, api_key: str) -> EmbedResult: ...

    def count_tokens(self, model: str, messages: ChatMessages) -> int:
        """Estimate the prompt tokens of `messages` for `model`. No network."""
        ...
