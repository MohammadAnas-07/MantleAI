"""Supported providers and what each can do."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ProviderInfo:
    id: str
    name: str
    supports_chat: bool
    supports_embeddings: bool


PROVIDERS: dict[str, ProviderInfo] = {
    p.id: p
    for p in [
        ProviderInfo("openai", "OpenAI", supports_chat=True, supports_embeddings=True),
        ProviderInfo("anthropic", "Anthropic", supports_chat=True, supports_embeddings=False),
        ProviderInfo("google", "Google", supports_chat=True, supports_embeddings=False),
        ProviderInfo("voyage", "Voyage AI", supports_chat=False, supports_embeddings=True),
    ]
}
