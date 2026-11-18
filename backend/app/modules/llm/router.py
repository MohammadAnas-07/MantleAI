"""llm endpoints (docs/api-outline.md, "LLM gateway"). Every query is scoped to the current user,
except the shared model catalog."""

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUserId, DbSession
from app.core.errors import AppError, NotFound
from app.core.repositories import AuditEventRepository
from app.modules.llm.gateway import Gateway
from app.modules.llm.models import ModelKind
from app.modules.llm.providers import PROVIDERS
from app.modules.llm.repository import (
    ModelConfigRepository,
    ProviderCredentialRepository,
    UsageRecordRepository,
    UserModelSettingsRepository,
)
from app.modules.llm.schemas import (
    CredentialCreate,
    CredentialOut,
    CredentialTestIn,
    CredentialTestOut,
    ModelOut,
    ModelPatch,
    ModelSettingsOut,
    ModelSettingsPatch,
    ProviderOut,
    UsageLine,
    UsageOut,
)
from app.modules.llm.service import get_gateway

router = APIRouter(tags=["llm"])

GatewayDep = Annotated[Gateway, Depends(get_gateway)]


# ---- providers and credentials -------------------------------------------------------------


@router.get("/providers")
async def list_providers(session: DbSession, user_id: CurrentUserId) -> list[ProviderOut]:
    with_keys = await ProviderCredentialRepository(session, user_id).providers_with_keys()
    return [
        ProviderOut(
            id=p.id,
            name=p.name,
            supports_chat=p.supports_chat,
            supports_embeddings=p.supports_embeddings,
            has_key=p.id in with_keys,
        )
        for p in PROVIDERS.values()
    ]


@router.get("/credentials")
async def list_credentials(session: DbSession, user_id: CurrentUserId) -> list[CredentialOut]:
    rows = await ProviderCredentialRepository(session, user_id).list(limit=200)
    return [CredentialOut.model_validate(r) for r in rows]


@router.post("/credentials", status_code=201)
async def add_credential(
    body: CredentialCreate, session: DbSession, user_id: CurrentUserId
) -> CredentialOut:
    if body.provider not in PROVIDERS:
        raise AppError(
            f"Unknown provider {body.provider!r}.",
            code="unknown_provider",
            status_code=422,
            details={"supported": sorted(PROVIDERS)},
        )
    credential = await ProviderCredentialRepository(session, user_id).add_key(
        provider=body.provider, label=body.label, api_key=body.api_key.get_secret_value()
    )
    await AuditEventRepository(session, user_id).add(
        event_type="credential.added",
        entity_type="provider_credential",
        entity_id=credential.id,
        details={"provider": credential.provider},
    )
    await session.commit()
    return CredentialOut.model_validate(credential)


@router.post("/credentials/{credential_id}/test")
async def test_credential(
    credential_id: uuid.UUID,
    body: CredentialTestIn,
    session: DbSession,
    user_id: CurrentUserId,
    gateway: GatewayDep,
) -> CredentialTestOut:
    """Make the smallest possible call with this key. Send `{}` as the body."""
    ok, error_code, model_id = await gateway.test_credential(session, user_id, credential_id)
    tested_at = datetime.now(UTC)
    await ProviderCredentialRepository(session, user_id).update(
        credential_id, last_tested_at=tested_at, last_test_ok=ok
    )
    await session.commit()
    return CredentialTestOut(ok=ok, error_code=error_code, model_id=model_id, tested_at=tested_at)


@router.delete("/credentials/{credential_id}", status_code=204)
async def delete_credential(
    credential_id: uuid.UUID, session: DbSession, user_id: CurrentUserId
) -> Response:
    repo = ProviderCredentialRepository(session, user_id)
    credential = await repo.get(credential_id)
    if credential is None:
        raise NotFound("Credential not found.")
    provider = credential.provider
    await repo.delete(credential_id)
    await AuditEventRepository(session, user_id).add(
        event_type="credential.deleted",
        entity_type="provider_credential",
        entity_id=credential_id,
        details={"provider": provider},
    )
    await session.commit()
    return Response(status_code=204)


# ---- model catalog -------------------------------------------------------------------------


@router.get("/models")
async def list_models(session: DbSession, user_id: CurrentUserId) -> list[ModelOut]:
    rows = await ModelConfigRepository(session).list(limit=500)
    return [ModelOut.model_validate(r) for r in rows]


@router.patch("/models/{model_id}")
async def update_model(
    model_id: uuid.UUID, body: ModelPatch, session: DbSession, user_id: CurrentUserId
) -> ModelOut:
    values = body.model_dump(exclude_none=True)
    repo = ModelConfigRepository(session)
    model = await repo.update(model_id, **values) if values else await repo.get(model_id)
    if model is None:
        raise NotFound("Model not found.")
    await session.commit()
    return ModelOut.model_validate(model)


# ---- model settings ------------------------------------------------------------------------


@router.get("/settings/models")
async def get_model_settings(session: DbSession, user_id: CurrentUserId) -> ModelSettingsOut:
    row = await UserModelSettingsRepository(session, user_id).get_for_user()
    if row is None:  # defaults; a GET never creates the row (rule 28)
        return ModelSettingsOut(
            utility_model_id=None, embedding_model_id=None, background_summary_enabled=True
        )
    return ModelSettingsOut(
        utility_model_id=row.utility_model_id,
        embedding_model_id=row.embedding_model_id,
        background_summary_enabled=row.background_summary_enabled,
    )


async def _check_model(session: AsyncSession, model_id: uuid.UUID | None, kind: ModelKind) -> None:
    if model_id is None:
        return
    model = await ModelConfigRepository(session).get(model_id)
    if model is None or model.kind != kind or not model.enabled:
        raise AppError(
            f"That model is not an enabled {kind.value} model.",
            code="model_unavailable",
            status_code=422,
        )


@router.patch("/settings/models")
async def update_model_settings(
    body: ModelSettingsPatch, session: DbSession, user_id: CurrentUserId
) -> ModelSettingsOut:
    values = body.model_dump(include=body.model_fields_set)
    if values.get("background_summary_enabled", True) is None:
        raise AppError("background_summary_enabled can't be null.", status_code=422)
    await _check_model(session, values.get("utility_model_id"), ModelKind.CHAT)
    await _check_model(session, values.get("embedding_model_id"), ModelKind.EMBEDDING)

    repo = UserModelSettingsRepository(session, user_id)
    row = await repo.get_for_user()
    if row is None:
        row = await repo.add(**values)
    elif values:
        row = await repo.update(row.id, **values)
    assert row is not None
    await session.commit()
    return ModelSettingsOut(
        utility_model_id=row.utility_model_id,
        embedding_model_id=row.embedding_model_id,
        background_summary_enabled=row.background_summary_enabled,
    )


# ---- usage ---------------------------------------------------------------------------------


@router.get("/usage")
async def usage_totals(
    session: DbSession,
    user_id: CurrentUserId,
    project_id: uuid.UUID | None = None,
    model_id: uuid.UUID | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
) -> UsageOut:
    """Totals grouped by purpose and trigger, so each background purpose is its own line."""
    rows = await UsageRecordRepository(session, user_id).totals(
        project_id=project_id, model_id=model_id, since=since, until=until
    )
    lines = [
        UsageLine(
            purpose=r.purpose,
            trigger=r.trigger,
            model_id=r.model_id,
            calls=r.calls,
            input_tokens=r.input_tokens,
            output_tokens=r.output_tokens,
            cost_usd=r.cost_usd,
        )
        for r in rows
    ]
    return UsageOut(
        lines=lines,
        total_calls=sum(line.calls for line in lines),
        total_input_tokens=sum(line.input_tokens for line in lines),
        total_output_tokens=sum(line.output_tokens for line in lines),
        total_cost_usd=sum((line.cost_usd or Decimal(0) for line in lines), Decimal(0)),
    )
