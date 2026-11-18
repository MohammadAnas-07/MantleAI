"""Repositories for the llm module. Every query on user data filters by user_id."""

import uuid
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import func, select

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

    async def latest_for_provider(self, provider: str) -> ProviderCredential | None:
        stmt = (
            self._select()
            .where(ProviderCredential.provider == provider)
            .order_by(ProviderCredential.created_at.desc(), ProviderCredential.id.desc())
            .limit(1)
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def providers_with_keys(self) -> set[str]:
        stmt = (
            select(ProviderCredential.provider)
            .where(ProviderCredential.user_id == self.user_id)
            .distinct()
        )
        return set((await self.session.execute(stmt)).scalars().all())


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

    async def totals(
        self,
        *,
        project_id: uuid.UUID | None = None,
        model_id: uuid.UUID | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> Sequence[Any]:
        """One row per (purpose, trigger, model): calls, tokens and cost."""
        stmt = select(
            UsageRecord.purpose,
            UsageRecord.trigger,
            UsageRecord.model_id,
            func.count().label("calls"),
            func.coalesce(func.sum(UsageRecord.input_tokens), 0).label("input_tokens"),
            func.coalesce(func.sum(UsageRecord.output_tokens), 0).label("output_tokens"),
            func.sum(UsageRecord.cost_usd).label("cost_usd"),
        ).where(UsageRecord.user_id == self.user_id)
        if project_id is not None:
            stmt = stmt.where(UsageRecord.project_id == project_id)
        if model_id is not None:
            stmt = stmt.where(UsageRecord.model_id == model_id)
        if since is not None:
            stmt = stmt.where(UsageRecord.created_at >= since)
        if until is not None:
            stmt = stmt.where(UsageRecord.created_at < until)
        stmt = stmt.group_by(UsageRecord.purpose, UsageRecord.trigger, UsageRecord.model_id)
        stmt = stmt.order_by(UsageRecord.purpose, UsageRecord.trigger)
        return (await self.session.execute(stmt)).all()
