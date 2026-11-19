"""Tables owned by the llm module (LLM gateway)."""

import uuid
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import ForeignKey, LargeBinary, Numeric, String, false, true
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Entity, UserOwnedEntity, fk, str_enum


class ModelKind(StrEnum):
    CHAT = "chat"
    EMBEDDING = "embedding"


class UsagePurpose(StrEnum):
    CHAT = "chat"
    ROLLING_SUMMARY = "rolling_summary"
    SWITCH_SUMMARY = "switch_summary"
    EMBEDDING = "embedding"
    AGENT = "agent"  # unused; agent and gap finder runs write agent_run
    AGENT_RUN = "agent_run"
    TEACHING = "teaching"
    KEY_TEST = "key_test"  # the tiny call made by "test key"


class UsageTrigger(StrEnum):
    USER = "user"  # the user directly asked for this call
    BACKGROUND = "background"  # they didn't; shown as its own line in the usage view (D10)


class UsageStatus(StrEnum):
    SUCCESS = "success"
    ERROR = "error"
    CANCELLED = "cancelled"


class ProviderCredential(UserOwnedEntity):
    """A provider API key. Only Fernet ciphertext is stored (see `crypto.py`)."""

    __tablename__ = "provider_credentials"

    provider: Mapped[str] = mapped_column(String(50))
    label: Mapped[str] = mapped_column(String(100), default="", server_default="")
    encrypted_key: Mapped[bytes] = mapped_column(LargeBinary)
    key_hint: Mapped[str] = mapped_column(String(4))
    last_tested_at: Mapped[datetime | None]
    last_test_ok: Mapped[bool | None]


class ModelConfig(Entity):
    """Shared model catalog. Reference data, not user data, so no `user_id`."""

    __tablename__ = "model_configs"

    provider: Mapped[str] = mapped_column(String(50))
    litellm_model: Mapped[str] = mapped_column(String(200), unique=True)
    display_name: Mapped[str] = mapped_column(String(200))
    kind: Mapped[ModelKind] = mapped_column(str_enum(ModelKind))
    context_window: Mapped[int]
    max_output_tokens: Mapped[int | None]
    embedding_dimensions: Mapped[int | None]
    # Whether the model accepts tool calls. When false, tool history is sent as plain text.
    supports_tools: Mapped[bool] = mapped_column(default=False, server_default=false())
    input_cost_per_mtok: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))
    output_cost_per_mtok: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))
    enabled: Mapped[bool] = mapped_column(default=True, server_default=true())


class UserModelSettings(UserOwnedEntity):
    """One row per user."""

    __tablename__ = "user_model_settings"

    # Overrides the base column: one row per user, and the unique constraint is the index.
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True
    )
    # Null means "use the conversation's active model" (D3).
    utility_model_id: Mapped[uuid.UUID | None] = mapped_column(
        fk("model_configs", ondelete="SET NULL"), index=True
    )
    # Null until the user picks one (the catalog may still be empty).
    embedding_model_id: Mapped[uuid.UUID | None] = mapped_column(
        fk("model_configs", ondelete="SET NULL"), index=True
    )
    # When false, no rolling-summary calls run in the background (D10).
    background_summary_enabled: Mapped[bool] = mapped_column(default=True, server_default=true())


class UsageRecord(UserOwnedEntity):
    """One row per LLM call, no exceptions. Kept when the project or conversation is deleted,
    so cost history stays complete."""

    __tablename__ = "usage_records"

    model_id: Mapped[uuid.UUID] = mapped_column(fk("model_configs"), index=True)
    purpose: Mapped[UsagePurpose] = mapped_column(str_enum(UsagePurpose))
    trigger: Mapped[UsageTrigger] = mapped_column(str_enum(UsageTrigger))
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        fk("projects", ondelete="SET NULL"), index=True
    )
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        fk("conversations", ondelete="SET NULL"), index=True
    )
    message_id: Mapped[uuid.UUID | None] = mapped_column(
        fk("messages", ondelete="SET NULL"), index=True
    )
    agent_run_id: Mapped[uuid.UUID | None] = mapped_column(
        fk("agent_runs", ondelete="SET NULL"), index=True
    )
    input_tokens: Mapped[int] = mapped_column(default=0, server_default="0")
    output_tokens: Mapped[int] = mapped_column(default=0, server_default="0")
    cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))
    latency_ms: Mapped[int | None]
    status: Mapped[UsageStatus] = mapped_column(str_enum(UsageStatus))
    error_code: Mapped[str | None] = mapped_column(String(64))
    # Sanitized structured fields of the provider's error (HTTP status, provider status and
    # code, quota id, retry delay). Never provider free text, prompts or keys.
    error_detail: Mapped[str | None] = mapped_column(String(255))
