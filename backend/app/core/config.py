"""Application settings, loaded from environment variables and backend/.env."""

from decimal import Decimal
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

    # Browser origins allowed to call the API (the Vite dev server). Never "*": any website the
    # user visits could otherwise read the local API's answers.
    # Host header values the API answers to. An entry without a port matches any port.
    # Anything else is refused, which stops DNS rebinding: a page on evil.example whose name
    # later resolves to 127.0.0.1 still sends "Host: evil.example".
    allowed_hosts: list[str] = Field(default_factory=lambda: ["localhost", "127.0.0.1"])
    cors_allowed_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:5173", "http://127.0.0.1:5173"]
    )

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

    # A rate limit is "quota exhausted" (never retried) when the provider asks for a wait
    # longer than this, or names a per-day quota. Shorter waits are ordinary rate limits.
    llm_quota_exhausted_min_wait_seconds: float = Field(default=600.0, ge=0)

    # ---- project indexing (rag) ----
    # Used when the user has not picked an embedding model in their settings.
    default_embedding_model: str = "gemini/gemini-embedding-001"
    # Files over this size, past this count, or with more segments than this are skipped.
    index_max_file_bytes: int = Field(default=1_000_000, ge=1)
    index_max_files: int = Field(default=20_000, ge=1)
    index_max_chunks_per_file: int = Field(default=200, ge=1)
    # Extra file name patterns (gitignore syntax) that are never read, on top of the built-in
    # sensitive list in app/modules/rag/secrets.py.
    index_sensitive_patterns: list[str] = Field(default_factory=list)
    # Indexing is refused above this estimated cost unless the request sends force=true.
    # An app setting in v0.1; it moves to the user's settings when auth arrives.
    index_cost_limit_usd: Decimal = Field(default=Decimal("1.00"), ge=0)

    # Splitting files into segments. Sizes are in characters (about 4 per token).
    chunk_max_chars: int = Field(default=4000, ge=200)
    chunk_min_chars: int = Field(default=200, ge=0)  # smaller segments merge with a neighbour
    chunk_window_lines: int = Field(default=60, ge=5)  # line-based splitting
    chunk_overlap_lines: int = Field(default=5, ge=0)

    # Embedding batches. Each batch is one provider call and one transaction.
    embed_batch_max_items: int = Field(default=64, ge=1)
    embed_batch_max_tokens: int = Field(default=16_000, ge=100)
    # Pause between batches, so free tiers with low per-minute limits keep up.
    embed_batch_delay_seconds: float = Field(default=1.0, ge=0)
    # On RateLimited: wait this long, doubling each time up to the cap, then give up.
    embed_rate_limit_backoff_seconds: float = Field(default=10.0, ge=0)
    embed_rate_limit_backoff_max_seconds: float = Field(default=120.0, ge=0)
    embed_max_retries: int = Field(default=5, ge=0)

    # Give up on an ordinary rate limit once the waits of one batch would pass this total.
    embed_retry_max_total_wait_seconds: float = Field(default=900.0, ge=0)

    # Retrieval.
    retrieval_top_k: int = Field(default=8, ge=1)
    retrieval_max_top_k: int = Field(default=50, ge=1)  # hard cap for any request
    retrieval_candidates: int = Field(default=50, ge=1)  # per search arm, before fusion
    retrieval_query_max_chars: int = Field(default=2000, ge=1)
    retrieval_rrf_k: int = Field(default=60, ge=1)
    # Share of the context budget the retrieved code may use.
    retrieved_max_share: float = Field(default=0.30, gt=0, le=1)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
