"""Application settings, loaded from environment variables and backend/.env."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/.env, no matter which folder you start the app from.
ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_FILE, env_file_encoding="utf-8", extra="ignore")

    app_env: str = "development"
    log_level: str = "INFO"
    database_url: str = "postgresql+asyncpg://mantle:mantle@127.0.0.1:5433/mantle"
    # Fernet key that encrypts provider API keys. Required; the app refuses to start without it.
    master_encryption_key: str = ""
    # Dimension of the pgvector `chunks.embedding` column. Changing it needs a new Alembic
    # migration (alter the column, rebuild the HNSW index) and re-indexing every project.
    # HNSW supports at most 2000 dimensions for the `vector` type.
    embedding_dimensions: int = Field(default=1536, ge=1, le=2000)

    # Context builder. Budget = context window - reserved output - safety margin (a share of the
    # context window, because token counts are estimates and tokenizers differ).
    context_reserved_output_tokens: int = Field(default=4096, ge=1)
    context_safety_margin: float = Field(default=0.10, ge=0, lt=1)
    # The latest user message and this many turns before it are never dropped.
    context_keep_recent_turns: int = Field(default=2, ge=0)

    # Rolling summary: runs when messages not yet covered pass this many tokens.
    summary_trigger_tokens: int = Field(default=2000, ge=1)
    summary_max_output_tokens: int = Field(default=1024, ge=1)

    # Project memory (requirements, decisions, tasks), written only by the user.
    memory_title_max_length: int = Field(default=200, ge=1, le=300)  # column is 300
    memory_text_max_length: int = Field(default=5000, ge=1)
    memory_max_items_per_kind: int = Field(default=500, ge=1)
    memory_page_max: int = Field(default=100, ge=1)

    # Pinned memory in the model context: a share of the context budget, a cap per kind, and a
    # cut-off for long items.
    pinned_max_share: float = Field(default=0.25, gt=0, le=1)
    pinned_max_decisions: int = Field(default=30, ge=0)
    pinned_max_requirements: int = Field(default=30, ge=0)
    pinned_max_tasks: int = Field(default=30, ge=0)
    pinned_item_max_chars: int = Field(default=600, ge=40)

    # A generation or summary lock older than this is treated as stale (crashed job).
    conversation_lock_timeout_seconds: int = Field(default=600, ge=1)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
