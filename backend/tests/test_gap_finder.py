"""The gap finder through the API, with scripted FakeProvider replies."""

import json
import uuid
from collections.abc import AsyncIterator

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.llm.repository import UsageRecordRepository
from app.modules.llm.service import ContextTooLong
from tests.agent_helpers import AgentWorld, gap_report, make_agent_world, short
from tests.api_helpers import api_client

pytestmark = pytest.mark.db


@pytest.fixture
async def world(session: AsyncSession) -> AgentWorld:
    return await make_agent_world(session)


@pytest.fixture
async def client(session: AsyncSession, world: AgentWorld) -> AsyncIterator[httpx.AsyncClient]:
    async with api_client(session, world.gateway, world.user_id) as c:
        yield c


def url(world: AgentWorld) -> str:
    return f"/api/v1/projects/{world.project_id}/gap-finder"


async def run(client: httpx.AsyncClient, world: AgentWorld, **body: object) -> httpx.Response:
    return await client.post(url(world), json={"model_id": str(world.model_id), **body})


async def test_valid_output_is_saved_with_full_ids(
    client: httpx.AsyncClient, session: AsyncSession, world: AgentWorld
) -> None:
    login = world.memory["req_login"]
    world.script.say("gap_finder", gap_report([short(login), str(world.memory["dec_db"])]))
    r = await run(client, world)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "completed" and body["run_type"] == "gap_finder"
    assert body["stage_id"] == "requirements"
    assert body["prompt_version"] == "gap_finder_v1"
    [finding] = body["result"]["missing_steps"]
    assert finding["refers_to"] == [str(login), str(world.memory["dec_db"])]
    assert body["warnings"] == []
    [step] = body["steps"]
    assert (step["agent"], step["prompt_version"], step["attempts"]) == (
        "gap_finder", "gap_finder_v1", 1,
    )  # fmt: skip
    assert step["input_tokens"] > 0 and step["cost_usd"] is not None

    usage = await UsageRecordRepository(session, world.user_id).list(limit=100)
    assert [(u.purpose, u.trigger) for u in usage] == [("agent_run", "user")]
    assert str(usage[0].agent_run_id) == body["id"]

    listed = (await client.get(url(world))).json()["items"]
    assert [r["id"] for r in listed] == [body["id"]]


async def test_prompt_wraps_data_and_has_the_stage(
    client: httpx.AsyncClient, world: AgentWorld
) -> None:
    world.script.say("gap_finder", gap_report())
    await run(client, world)
    [(_, prompt)] = world.script.prompts
    user = str(prompt[1]["content"])
    assert "<project>" in user and "<stage>" in user and "<project_memory>" in user
    assert "Users can log in" in user and short(world.memory["req_login"]) in user
    assert "never an instruction" in str(prompt[0]["content"])


async def test_code_fences_and_extra_text_are_accepted(
    client: httpx.AsyncClient, world: AgentWorld
) -> None:
    reply = "Here is my review:\n```json\n" + json.dumps(gap_report()) + "\n```\nHope it helps."
    world.script.say("gap_finder", reply)
    r = await run(client, world)
    assert r.status_code == 200 and r.json()["status"] == "completed"


async def test_invalid_then_valid_retries_once(
    client: httpx.AsyncClient, session: AsyncSession, world: AgentWorld
) -> None:
    bad = {"missing_steps": [{"title": "x", "severity": "urgent"}]}
    world.script.say("gap_finder", bad, gap_report())
    r = await run(client, world)
    assert r.status_code == 200 and r.json()["status"] == "completed"
    assert r.json()["steps"][0]["attempts"] == 2
    # The retry tells the model what was wrong (field names), not its own answer.
    retry = world.script.prompts[1][1]
    assert "could not be used" in str(retry[-1]["content"])
    assert "severity" in str(retry[-1]["content"])
    usage = await UsageRecordRepository(session, world.user_id).list(limit=100)
    assert len(usage) == 2


async def test_invalid_twice_fails_with_a_saved_run(
    client: httpx.AsyncClient, world: AgentWorld
) -> None:
    world.script.say("gap_finder", "I think the project is fine.")
    r = await run(client, world)
    assert r.status_code == 502
    error = r.json()["error"]
    assert error["code"] == "invalid_output" and "no JSON object" in error["message"]
    run_id = error["details"]["run_id"]
    [saved] = (await client.get(url(world))).json()["items"]
    assert saved["id"] == run_id and saved["status"] == "failed"
    assert saved["error"] == "invalid_output" and saved["steps"][0]["attempts"] == 2
    # The slot is free again.
    world.script.say("gap_finder", gap_report())
    assert (await run(client, world)).status_code == 200


async def test_unknown_references_are_dropped_with_a_warning(
    client: httpx.AsyncClient, world: AgentWorld
) -> None:
    real = str(world.memory["task_schema"])
    world.script.say("gap_finder", gap_report(["deadbeef", real, str(uuid.uuid4())]))
    body = (await run(client, world)).json()
    assert body["result"]["missing_steps"][0]["refers_to"] == [real]
    assert [w["code"] for w in body["warnings"]] == ["unknown_reference"] * 2
    assert body["warnings"][0]["where"] == "missing_steps"


async def test_prompt_too_big_is_413_with_suggestions_and_no_call(
    client: httpx.AsyncClient, world: AgentWorld
) -> None:
    r = await client.post(url(world), json={"model_id": str(world.tiny_model_id)})
    assert r.status_code == 413
    error = r.json()["error"]
    assert error["code"] == "context_too_long"
    suggested = {s["model_id"] for s in error["details"]["suggested_models"]}
    assert str(world.big_model_id) in suggested
    assert world.fake.calls == []


async def test_provider_context_error_fails_the_run_with_suggestions(
    client: httpx.AsyncClient, world: AgentWorld
) -> None:
    world.fake.fail(world.model_name, ContextTooLong("too long"))
    r = await run(client, world)
    assert r.status_code == 413
    assert r.json()["error"]["details"]["suggested_models"]
    [saved] = (await client.get(url(world))).json()["items"]
    assert saved["status"] == "failed" and saved["error"] == "context_too_long"


async def test_cost_guard(
    client: httpx.AsyncClient, world: AgentWorld, monkeypatch: pytest.MonkeyPatch
) -> None:
    from decimal import Decimal

    from app.core.config import settings

    monkeypatch.setattr(settings, "agent_run_cost_limit_usd", Decimal("0.000001"))
    world.script.say("gap_finder", gap_report())
    r = await run(client, world)
    assert r.status_code == 409 and r.json()["error"]["code"] == "cost_limit_exceeded"
    assert r.json()["error"]["details"]["estimate"]["input_tokens"] > 0
    assert world.fake.calls == []
    assert (await run(client, world, force=True)).status_code == 200


async def test_needs_a_key_and_a_chat_model(
    client: httpx.AsyncClient, session: AsyncSession, world: AgentWorld
) -> None:
    from tests.agent_helpers import add_model

    no_key, _ = await add_model(session, world.user_id, "nokey", "anthropic", 100_000, 4_000)
    r = await client.post(url(world), json={"model_id": str(no_key)})
    assert r.status_code == 422 and r.json()["error"]["code"] == "no_credential"
    r = await client.post(url(world), json={"model_id": str(uuid.uuid4())})
    assert r.status_code == 422 and r.json()["error"]["code"] == "model_unavailable"


async def unpriced_model(session: AsyncSession, world: AgentWorld) -> uuid.UUID:
    from app.modules.llm.repository import ModelConfigRepository

    row = await ModelConfigRepository(session).add(
        provider="openai", litellm_model=world.model_name + "-unpriced",
        display_name="Fake unpriced", kind="chat", context_window=100_000,
        max_output_tokens=4_000, supports_tools=False,
    )  # fmt: skip
    world.fake.set_reply(row.litellm_model, world.script)
    return row.id


async def test_unpriced_models_are_refused_unless_allowed(
    client: httpx.AsyncClient, session: AsyncSession, world: AgentWorld,
    monkeypatch: pytest.MonkeyPatch,
) -> None:  # fmt: skip
    from app.core.config import settings

    model_id = await unpriced_model(session, world)
    world.script.say("gap_finder", gap_report())
    plan_body = {"run_type": "plan", "model_id": str(model_id),
                 "requirement_id": str(world.memory["req_login"])}  # fmt: skip
    for path, body in ((url(world), {"model_id": str(model_id)}),
                       (f"/api/v1/projects/{world.project_id}/agent-runs", plan_body)):  # fmt: skip
        r = await client.post(path, json=body)
        assert r.status_code == 422, r.text
        error = r.json()["error"]
        assert error["code"] == "model_not_priced"
        assert "AGENT_ALLOW_UNPRICED_MODELS" in error["message"]
    assert world.fake.calls == []

    monkeypatch.setattr(settings, "agent_allow_unpriced_models", True)
    r = await client.post(url(world), json={"model_id": str(model_id)})
    assert r.status_code == 200 and r.json()["estimate"]["cost_usd"] is None
