"""Repositories for the llm module. Every query on user data filters by user_id."""

from typing import Any

from app.db.repository import Repository, UserScopedRepository
from app.modules.llm.crypto import encrypt_secret, key_hint
from app.modules.llm.models import ModelConfig, ProviderCredential, UsageRecord, UserModelSettings


class ProviderCredentialRepository(UserScopedRepository[ProviderCredential]):
    """Takes a plaintext key, stores only its Fernet ciphertext and last-4 hint."""

    model = ProviderCredential

    async def add_key(self, *, provider: str, api_key: str, label: str = "") -> ProviderCredential:
        return await super().add(
            provider=provider,
            label=label,
            encrypted_key=encrypt_secret(api_key),
            key_hint=key_hint(api_key),
        )

    async def add(self, **values: Any) -> ProviderCredential:
        raise TypeError("Use add_key(); a credential must be created from a plaintext key.")


class ModelConfigRepository(Repository[ModelConfig]):
    """Shared catalog, not user data, so not scoped by user."""

    model = ModelConfig

    async def get_by_litellm_model(self, litellm_model: str) -> ModelConfig | None:
        rows = await self.list(litellm_model=litellm_model, limit=1)
        return rows[0] if rows else None


class UserModelSettingsRepository(UserScopedRepository[UserModelSettings]):
    model = UserModelSettings

    async def get_for_user(self) -> UserModelSettings | None:
        rows = await self.list(limit=1)
        return rows[0] if rows else None


class UsageRecordRepository(UserScopedRepository[UsageRecord]):
    model = UsageRecord
