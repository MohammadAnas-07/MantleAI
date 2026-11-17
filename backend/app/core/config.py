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


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
