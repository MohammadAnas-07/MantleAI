"""The interface every LLM backend implements: LiteLLM for real calls, FakeProvider for tests.

Messages are OpenAI-style dicts (`{"role": ..., "content": "..."}`). The gateway handles keys,
usage records and logging; a backend only talks to the provider.
"""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, Literal, Protocol

ChatMessages = list[dict[str, Any]]

# "document" for text that is stored and searched, "query" for the search text itself.
EmbedInputType = Literal["document", "query"]


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

    async def embed(
        self,
        model: str,
        texts: list[str],
        *,
        api_key: str,
        dimensions: int | None = None,
        input_type: EmbedInputType | None = None,
    ) -> EmbedResult:
        """Embed `texts`. `dimensions` asks for vectors of that size; `input_type` says whether
        the texts are documents to store or a search query (providers that support it embed
        the two differently). Raises only LLMError subclasses."""
        ...

    def count_tokens(self, model: str, messages: ChatMessages) -> int:
        """Estimate the prompt tokens of `messages` for `model`. No network."""
        ...
