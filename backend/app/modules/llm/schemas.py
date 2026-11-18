"""Request and response bodies for the llm endpoints. No response ever holds an API key."""

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, SecretStr


class ProviderOut(BaseModel):
    id: str
    name: str
    supports_chat: bool
    supports_embeddings: bool
    has_key: bool


class CredentialCreate(BaseModel):
    provider: str
    label: str = Field(default="", max_length=100)
    # SecretStr keeps the key out of reprs, logs and error messages.
    api_key: SecretStr = Field(min_length=8, max_length=500)


class CredentialOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    provider: str
    label: str
    key_hint: str  # last 4 characters only
    last_tested_at: datetime | None
    last_test_ok: bool | None
    created_at: datetime


class CredentialTestIn(BaseModel):
    """Empty on purpose. A JSON body makes clients (and /docs) send
    `Content-Type: application/json`, which every write request must have (rule 29)."""

    model_config = ConfigDict(extra="forbid", json_schema_extra={"example": {}})


class CredentialTestOut(BaseModel):
    ok: bool
    error_code: str | None
    model_id: uuid.UUID
    tested_at: datetime


class ModelOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    provider: str
    litellm_model: str
    display_name: str
    kind: str
    context_window: int
    max_output_tokens: int | None
    embedding_dimensions: int | None
    supports_tools: bool
    input_cost_per_mtok: Decimal | None
    output_cost_per_mtok: Decimal | None
    enabled: bool


class ModelPatch(BaseModel):
    enabled: bool | None = None
    context_window: int | None = Field(default=None, gt=0)


class ModelSettingsOut(BaseModel):
    utility_model_id: uuid.UUID | None  # null = use the conversation's active model
    embedding_model_id: uuid.UUID | None
    background_summary_enabled: bool


class ModelSettingsPatch(BaseModel):
    utility_model_id: uuid.UUID | None = None
    embedding_model_id: uuid.UUID | None = None
    background_summary_enabled: bool | None = None


class UsageLine(BaseModel):
    purpose: str
    trigger: str
    model_id: uuid.UUID
    calls: int
    input_tokens: int
    output_tokens: int
    cost_usd: Decimal | None


class UsageOut(BaseModel):
    lines: list[UsageLine]
    total_calls: int
    total_input_tokens: int
    total_output_tokens: int
    total_cost_usd: Decimal
