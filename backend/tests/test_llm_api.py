"""llm endpoint tests: FakeProvider gateway, test database, no keys, no network."""

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.repositories import AuditEventRepository
from app.db.seed import seed_default_user
from app.modules.llm.catalog import seed_default_models
from app.modules.llm.fake import FakeProvider
from app.modules.llm.gateway import Gateway
from app.modules.llm.models import UsagePurpose, UsageTrigger
from app.modules.llm.repository import (
    ModelConfigRepository,
    ProviderCredentialRepository,
    UsageRecordRepository,
)
from app.modules.llm.service import AuthFailed
from tests.api_helpers import api_client
from tests.graph import make_user

pytestmark = pytest.mark.db

KEY = "sk-test-not-real-key-9999wxyz"


@pytest.fixture
def fake() -> FakeProvider:
    return FakeProvider()


@pytest.fixture
def gateway(fake: FakeProvider) -> Gateway:
    return Gateway(fake)


@pytest.fixture
async def alice(session: AsyncSession) -> uuid.UUID:
    await seed_default_models(session)
    return await make_user(session, "Alice")


@pytest.fixture
async def bob(session: AsyncSession) -> uuid.UUID:
    return await make_user(session, "Bob")


async def model_id(session: AsyncSession, litellm_model: str) -> uuid.UUID:
    model = await ModelConfigRepository(session).get_by_litellm_model(litellm_model)
    assert model is not None
    return model.id


async def test_add_list_and_delete_credential(
    session: AsyncSession, gateway: Gateway, alice: uuid.UUID
) -> None:
    async with api_client(session, gateway, alice) as client:
        created = await client.post(
            "/api/v1/credentials", json={"provider": "openai", "label": "main", "api_key": KEY}
        )
        assert created.status_code == 201
        body = created.json()
        assert body["key_hint"] == "wxyz"
        assert "api_key" not in body and "encrypted_key" not in body
        assert KEY not in created.text

        listed = await client.get("/api/v1/credentials")
        assert [c["id"] for c in listed.json()] == [body["id"]]
        assert KEY not in listed.text

        providers = {p["id"]: p for p in (await client.get("/api/v1/providers")).json()}
        assert providers["openai"]["has_key"] is True
        assert providers["anthropic"]["has_key"] is False
        assert providers["voyage"]["supports_chat"] is False

        assert (await client.delete(f"/api/v1/credentials/{body['id']}")).status_code == 204
        again = await client.delete(f"/api/v1/credentials/{body['id']}")
        assert again.status_code == 404
        assert again.json()["error"]["code"] == "not_found"

    events = await AuditEventRepository(session, alice).list()
    # Same transaction, same now(): compare as a set, not in order.
    assert sorted(e.event_type for e in events) == ["credential.added", "credential.deleted"]
    assert all(KEY not in str(e.details) for e in events)


async def test_bad_credential_requests_never_echo_the_key(
    session: AsyncSession, gateway: Gateway, alice: uuid.UUID
) -> None:
    async with api_client(session, gateway, alice) as client:
        unknown = await client.post(
            "/api/v1/credentials", json={"provider": "nope", "api_key": KEY}
        )
        assert unknown.status_code == 422
        assert unknown.json()["error"]["code"] == "unknown_provider"

        invalid = await client.post("/api/v1/credentials", json={"api_key": KEY})  # no provider
        assert invalid.status_code == 422
        assert invalid.json()["error"]["code"] == "validation_error"
        assert KEY not in invalid.text

        not_json = await client.post(
            "/api/v1/credentials", content=f"provider=openai&api_key={KEY}",
            headers={"content-type": "application/x-www-form-urlencoded"},
        )  # fmt: skip
        assert not_json.status_code == 415
        assert not_json.json()["error"]["code"] == "unsupported_media_type"


async def test_test_credential_calls_only_that_provider(
    session: AsyncSession, gateway: Gateway, fake: FakeProvider, alice: uuid.UUID
) -> None:
    async with api_client(session, gateway, alice) as client:
        cred = (
            await client.post("/api/v1/credentials", json={"provider": "anthropic", "api_key": KEY})
        ).json()
        ok = await client.post(f"/api/v1/credentials/{cred['id']}/test", json={})
        assert ok.status_code == 200
        assert ok.json()["ok"] is True
        assert [c.model.split("/")[0] for c in fake.calls] == ["anthropic"]
        assert fake.calls[0].max_tokens == 1

        fake.fail(fake.calls[0].model, AuthFailed("bad key"))
        bad = await client.post(f"/api/v1/credentials/{cred['id']}/test", json={})
        assert bad.json() == {**bad.json(), "ok": False, "error_code": "auth_failed"}

        listed = (await client.get("/api/v1/credentials")).json()
        assert listed[0]["last_test_ok"] is False

    rows = await UsageRecordRepository(session, alice).list()
    assert {(r.purpose, r.trigger) for r in rows} == {("key_test", "user")}


async def test_models_and_settings(
    session: AsyncSession, gateway: Gateway, alice: uuid.UUID
) -> None:
    gpt = await model_id(session, "openai/gpt-5.6")
    embed = await model_id(session, "openai/text-embedding-3-small")
    async with api_client(session, gateway, alice) as client:
        models = {m["litellm_model"]: m for m in (await client.get("/api/v1/models")).json()}
        assert models["openai/gpt-5.6"]["supports_tools"] is True
        assert models["voyage/voyage-4-lite"]["enabled"] is False  # 1024 dims != 1536 column

        patched = await client.patch(f"/api/v1/models/{gpt}", json={"context_window": 8000})
        assert patched.json()["context_window"] == 8000
        missing = await client.patch(f"/api/v1/models/{uuid.uuid4()}", json={"enabled": False})
        assert missing.status_code == 404

        defaults = (await client.get("/api/v1/settings/models")).json()
        assert defaults == {
            "utility_model_id": None,
            "embedding_model_id": None,
            "background_summary_enabled": True,
        }
        updated = await client.patch(
            "/api/v1/settings/models",
            json={"utility_model_id": str(gpt), "background_summary_enabled": False},
        )
        assert updated.json()["utility_model_id"] == str(gpt)
        assert updated.json()["background_summary_enabled"] is False

        wrong_kind = await client.patch(
            "/api/v1/settings/models", json={"utility_model_id": str(embed)}
        )
        assert wrong_kind.status_code == 422

        reset = await client.patch("/api/v1/settings/models", json={"utility_model_id": None})
        assert reset.json()["utility_model_id"] is None
        assert reset.json()["background_summary_enabled"] is False


async def test_usage_is_grouped_by_purpose_and_trigger(
    session: AsyncSession, gateway: Gateway, alice: uuid.UUID
) -> None:
    gpt = await model_id(session, "openai/gpt-5.6")
    await ProviderCredentialRepository(session, alice).add_key(provider="openai", api_key=KEY)
    for purpose, trigger in [
        (UsagePurpose.CHAT, UsageTrigger.USER),
        (UsagePurpose.CHAT, UsageTrigger.USER),
        (UsagePurpose.ROLLING_SUMMARY, UsageTrigger.BACKGROUND),
    ]:
        await gateway.complete(
            session, alice, gpt, [{"role": "user", "content": "x"}],
            purpose=purpose, trigger=trigger,
        )  # fmt: skip

    async with api_client(session, gateway, alice) as client:
        usage = (await client.get("/api/v1/usage")).json()
    lines = {(line["purpose"], line["trigger"]): line for line in usage["lines"]}
    assert lines[("chat", "user")]["calls"] == 2
    assert lines[("rolling_summary", "background")]["calls"] == 1
    assert usage["total_calls"] == 3


async def test_user_isolation_on_every_endpoint(
    session: AsyncSession, gateway: Gateway, fake: FakeProvider, alice: uuid.UUID, bob: uuid.UUID
) -> None:
    gpt = await model_id(session, "openai/gpt-5.6")
    async with api_client(session, gateway, alice) as as_alice:
        cred = (
            await as_alice.post("/api/v1/credentials", json={"provider": "openai", "api_key": KEY})
        ).json()
        await as_alice.patch("/api/v1/settings/models", json={"utility_model_id": str(gpt)})
        await as_alice.post(f"/api/v1/credentials/{cred['id']}/test", json={})

    async with api_client(session, gateway, bob) as as_bob:
        assert (await as_bob.get("/api/v1/credentials")).json() == []
        providers = (await as_bob.get("/api/v1/providers")).json()
        assert not any(p["has_key"] for p in providers)
        test = await as_bob.post(f"/api/v1/credentials/{cred['id']}/test", json={})
        assert test.status_code == 404
        assert (await as_bob.delete(f"/api/v1/credentials/{cred['id']}")).status_code == 404
        settings = (await as_bob.get("/api/v1/settings/models")).json()
        assert settings["utility_model_id"] is None
        assert (await as_bob.get("/api/v1/usage")).json()["total_calls"] == 0
        me = (await as_bob.get("/api/v1/me")).json()
        assert me["display_name"] == "Bob"

    assert len(fake.calls) == 1  # only Alice's test call reached the provider
    assert await ProviderCredentialRepository(session, alice).get(uuid.UUID(cred["id"]))


async def test_current_user_is_the_seeded_default_user(
    session: AsyncSession, gateway: Gateway
) -> None:
    async with api_client(session, gateway, None) as client:
        missing = await client.get("/api/v1/me")
        assert missing.status_code == 503
        assert missing.json()["error"]["code"] == "not_seeded"

        await seed_default_user(session)
        me = await client.get("/api/v1/me")
        assert me.status_code == 200
        assert me.json()["is_local_default"] is True
