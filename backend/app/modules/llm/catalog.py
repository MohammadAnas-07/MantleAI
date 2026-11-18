"""The default model catalog, added by the seed script.

Values (context window, max output, costs, tool support) were copied from LiteLLM 1.110.0's
bundled model data on 2026-11-18, so seeding needs no network and no `litellm` import. The user
can change `enabled` and `context_window` later through `PATCH /api/v1/models/{id}`.
"""

from dataclasses import asdict, dataclass
from decimal import Decimal

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.modules.llm.models import ModelConfig, ModelKind


@dataclass(frozen=True)
class CatalogEntry:
    provider: str
    litellm_model: str
    display_name: str
    kind: ModelKind
    context_window: int
    max_output_tokens: int | None
    supports_tools: bool
    input_cost_per_mtok: Decimal | None
    output_cost_per_mtok: Decimal | None
    embedding_dimensions: int | None = None


def _d(value: str) -> Decimal:
    return Decimal(value)


CHAT = ModelKind.CHAT
EMBED = ModelKind.EMBEDDING

DEFAULT_MODELS: list[CatalogEntry] = [
    CatalogEntry("anthropic", "anthropic/claude-sonnet-5-5", "Claude Sonnet 5.5", CHAT,
                 1_000_000, 128_000, True, _d("2"), _d("10")),
    CatalogEntry("anthropic", "anthropic/claude-opus-5-5", "Claude Opus 5.5", CHAT,
                 1_000_000, 128_000, True, _d("4"), _d("20")),
    CatalogEntry("openai", "openai/gpt-5.6", "GPT-5.6", CHAT,
                 922_000, 128_000, True, _d("4"), _d("20")),
    CatalogEntry("openai", "openai/gpt-5.6-luna", "GPT-5.6 Luna", CHAT,
                 922_000, 128_000, True, _d("0.2"), _d("1.2")),
    CatalogEntry("google", "gemini/gemini-3.8-flash", "Gemini 3.8 Flash", CHAT,
                 1_048_576, 65_536, True, _d("0.75"), _d("3.75")),
    # A second Google chat model, so the switch demo can run with only a free Gemini key.
    CatalogEntry("google", "gemini/gemini-3.5-flash-lite", "Gemini 3.5 Flash Lite", CHAT,
                 1_048_576, 65_536, True, _d("0.3"), _d("2.5")),
    CatalogEntry("openai", "openai/text-embedding-3-small", "OpenAI text-embedding-3-small", EMBED,
                 8_191, None, False, _d("0.02"), _d("0"), embedding_dimensions=1536),
    # Native size 3072; the gateway asks for EMBEDDING_DIMENSIONS (1536) through `dimensions`.
    # LiteLLM 1.110.0 data: max input 2048 tokens, $0.15 per million input tokens.
    CatalogEntry("google", "gemini/gemini-embedding-001", "Gemini Embedding 001", EMBED,
                 2_048, None, False, _d("0.15"), _d("0"), embedding_dimensions=1536),
    CatalogEntry("voyage", "voyage/voyage-4-lite", "Voyage 4 Lite", EMBED,
                 32_000, None, False, _d("0.02"), _d("0"), embedding_dimensions=1024),
]  # fmt: skip


def is_usable(entry: CatalogEntry) -> bool:
    """An embedding model is usable only if its dimension matches the vector column."""
    if entry.kind == ModelKind.EMBEDDING:
        return entry.embedding_dimensions == settings.embedding_dimensions
    return True


async def seed_default_models(session: AsyncSession) -> int:
    """Insert missing catalog models. Existing rows (and user changes) are left alone.

    Returns how many rows were created.
    """
    created = 0
    for entry in DEFAULT_MODELS:
        stmt = (
            insert(ModelConfig)
            .values(**asdict(entry), enabled=is_usable(entry))
            .on_conflict_do_nothing(index_elements=[ModelConfig.litellm_model])
        )
        result = await session.execute(stmt)
        created += result.rowcount
    return created
