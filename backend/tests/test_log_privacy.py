"""No message text, memory, code, file path or key in logs or stored error fields (audit A-005).

Each test puts a unique marker into user data, forces a failure path, and checks that the
marker shows up in no log line and no stored error field. One test checks the log line of a
normal call. Failures are forced with the fake provider and monkeypatches; no key, no network.
"""

import logging
import uuid
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import SecretMaskingFilter, setup_logging
from app.modules.conversations.repository import MessageRepository
from app.modules.llm.gateway import Gateway
from app.modules.llm.models import UsageRecord
from app.modules.llm.service import ProviderUnavailable
from app.modules.projects.repository import MemoryItemRepository
from tests.api_helpers import api_client, parse_sse
from tests.conversation_helpers import World, make_world, summarizer_provider
from tests.db_guard import guarded_engine


def marker() -> str:
    return "zebra" + uuid.uuid4().hex[:12]


# ---- second line of defence: settings, the engine and the filter -------------------------------


def test_settings_never_print_the_master_key_or_the_database_password() -> None:
    shown = repr(settings) + str(settings)
    assert settings.master_encryption_key and settings.master_encryption_key not in shown
    assert "database_url" not in shown and ":mantle@" not in shown


async def test_the_app_engine_keeps_sql_parameters_out_of_errors(migrated_database: Any) -> None:
    from app.db.session import engine

    assert engine.sync_engine.hide_parameters is True
    secret = marker()
    probe = guarded_engine(migrated_database, hide_parameters=True)
    try:
        async with probe.connect() as conn:
            with pytest.raises(DBAPIError) as info:
                await conn.execute(text("SELECT CAST(:v AS integer)"), {"v": secret})
    finally:
        await probe.dispose()
    # hide_parameters drops SQLAlchemy's "[parameters: ...]" part. PostgreSQL's own message
    # can still quote the bad value, which is why the code logs exception types only.
    assert "[parameters:" not in str(info.value)
    assert "hidden due to hide_parameters" in str(info.value)


def test_the_filter_masks_tracebacks_keys_and_sql_parameters() -> None:
    secret = marker()
    key = "sk-" + "test" + "A" * 24
    try:
        raise RuntimeError(f"failed with {key} [parameters: ('{secret} ] more',)]")
    except RuntimeError:
        import sys

        record = logging.LogRecord("x", logging.ERROR, __file__, 1, "boom %s", (key,),
                                   sys.exc_info())  # fmt: skip
    SecretMaskingFilter().filter(record)
    out = logging.Formatter().format(record)
    assert key not in out and secret not in out
    assert "RuntimeError" in out  # the type stays, for debugging


def test_the_filter_is_on_uvicorns_handlers_too() -> None:
    logger = logging.getLogger("uvicorn")
    handler = logging.StreamHandler()
    logger.addHandler(handler)
    try:
        setup_logging("INFO")
        assert any(isinstance(f, SecretMaskingFilter) for f in handler.filters)
    finally:
        logger.removeHandler(handler)


# ---- first line: failure paths with user data ---------------------------------------------------


@pytest.fixture
async def world(session: AsyncSession) -> World:
    return await make_world(session)


@pytest.mark.db
async def test_a_provider_error_in_chat_leaves_no_message_or_memory_text(
    session: AsyncSession, world: World, caplog: pytest.LogCaptureFixture
) -> None:
    secret = marker()
    await MemoryItemRepository(session, world.user_id).add(
        project_id=world.project_id, kind="decision", title=f"Use {secret}", status="accepted",
        body=f"because {secret}",
    )  # fmt: skip
    fake = summarizer_provider(world.litellm("small"))
    fake.fail(world.litellm("small"), ProviderUnavailable(f"upstream echoed {secret}"))
    caplog.set_level(logging.DEBUG)
    async with api_client(session, Gateway(fake), world.user_id) as client:
        r = await client.post(f"/api/v1/conversations/{world.conversation_id}/messages",
                              json={"content": f"Tell me about {secret}"})  # fmt: skip
    assert parse_sse(r.text)[-1][0] == "error"
    [_, reply] = await MessageRepository(session, world.user_id).in_order(world.conversation_id)
    usage = list(
        await session.scalars(select(UsageRecord).where(UsageRecord.user_id == world.user_id))
    )
    stored = [reply.error_code, *(u.error_code for u in usage), *(u.error_detail for u in usage)]
    assert secret not in caplog.text
    assert all(secret not in str(v) for v in stored)


@pytest.mark.db
async def test_a_validation_error_never_echoes_the_input(
    session: AsyncSession, world: World, caplog: pytest.LogCaptureFixture
) -> None:
    secret = marker()
    caplog.set_level(logging.DEBUG)
    async with api_client(session, Gateway(summarizer_provider()), world.user_id) as client:
        url = f"/api/v1/projects/{world.project_id}/memory"
        bad_status = await client.post(url, json={"kind": "task", "title": secret,
                                                  "status": secret})  # fmt: skip
        too_long = await client.post(url, json={"kind": "task", "title": secret * 40})
    for r in (bad_status, too_long):
        assert r.status_code == 422 and secret not in r.text
    assert secret not in caplog.text


@pytest.mark.db
async def test_a_provider_key_never_reaches_a_log_or_a_response(
    session: AsyncSession, world: World, caplog: pytest.LogCaptureFixture
) -> None:
    key = "sk-test-" + marker()
    caplog.set_level(logging.DEBUG)
    async with api_client(session, Gateway(summarizer_provider()), world.user_id) as client:
        body = {"provider": "openai", "label": "x", "api_key": key}
        saved = await client.post("/api/v1/credentials", json=body)
        listed = await client.get("/api/v1/credentials")
    assert saved.status_code == 201
    assert key not in saved.text and key not in listed.text and key not in caplog.text


@pytest.mark.db
async def test_agent_job_crash_and_cancel_leave_no_requirement_text(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    from app.modules.workflow import runs
    from app.modules.workflow.models import AgentRun
    from app.modules.workflow.steps import RunCancelled
    from tests.agent_helpers import make_agent_world

    agents = await make_agent_world(session)
    secret = marker()
    caplog.set_level(logging.DEBUG)

    async def crash(*_: object, **__: object) -> None:
        raise RuntimeError(f"model said {secret}")

    async def cancel(*_: object, **__: object) -> None:
        raise RunCancelled

    async with api_client(session, agents.gateway, agents.user_id) as client:
        for failing in (crash, cancel):
            monkeypatch.setattr(runs, "run_step", failing)
            r = await client.post(f"/api/v1/projects/{agents.project_id}/agent-runs", json={
                "run_type": "plan", "model_id": str(agents.model_id),
                "requirement_text": f"Build {secret}"})  # fmt: skip
            assert r.status_code == 202, r.text
            run = await session.get(AgentRun, uuid.UUID(r.json()["id"]))
            assert run is not None
            await session.refresh(run)
            assert run.status in ("failed", "cancelled")
            fields = [run.error, run.error_message, str(run.error_details)]
            assert all(secret not in str(v) for v in fields)
    assert secret not in caplog.text


@pytest.mark.db
async def test_index_paths_content_and_crashes_leave_no_trace_in_logs(
    session: AsyncSession, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:  # fmt: skip
    from app.modules.rag import indexer
    from tests.rag_helpers import copy_fixture, fast_settings, index_once, make_rag_world

    fast_settings(monkeypatch)
    root = copy_fixture(tmp_path)
    secret = marker()
    (root / "backend" / "app" / f"{secret}.py").write_text(f"def f():\n    return '{secret}'\n")
    rag = await make_rag_world(session, root)
    caplog.set_level(logging.DEBUG)
    run = await index_once(session, rag)
    assert run.status == "succeeded"

    async def crash(*_: object, **__: object) -> None:
        raise RuntimeError(f"failed on {secret}")

    monkeypatch.setattr(indexer, "_execute", crash)
    crashed = await index_once(session, rag, force=True)
    assert (crashed.status, crashed.error) == ("failed", "internal_error")
    assert secret not in caplog.text


@pytest.mark.db
async def test_a_normal_chat_call_logs_metadata_only(
    session: AsyncSession, world: World, caplog: pytest.LogCaptureFixture
) -> None:
    secret = marker()
    fake = summarizer_provider()
    fake.set_reply(world.litellm("small"), f"Reply with {secret}")
    caplog.set_level(logging.INFO)
    async with api_client(session, Gateway(fake), world.user_id) as client:
        r = await client.post(f"/api/v1/conversations/{world.conversation_id}/messages",
                              json={"content": f"Question {secret}"})  # fmt: skip
    assert parse_sse(r.text)[-1][0] == "message_end"
    calls = [m for m in caplog.messages if m.startswith("llm call ")]
    assert len(calls) == 1
    assert "purpose=chat" in calls[0] and "status=success" in calls[0]
    assert "input_tokens=" in calls[0] and "latency_ms=" in calls[0]
    assert secret not in caplog.text
