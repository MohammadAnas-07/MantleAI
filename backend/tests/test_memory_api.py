"""Project memory endpoints: CRUD, validation, pagination, limits, isolation, logs."""

import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.modules.llm.fake import FakeProvider
from app.modules.llm.gateway import Gateway
from app.modules.projects.models import MemoryDependency, MemoryItem
from app.modules.projects.repository import ProjectRepository
from tests.api_helpers import api_client
from tests.graph import make_user

pytestmark = pytest.mark.db


@pytest.fixture
def gateway() -> Gateway:
    return Gateway(FakeProvider())


@pytest.fixture
async def owner(session: AsyncSession) -> dict[str, uuid.UUID]:
    user = await make_user(session, "Owner")
    projects = ProjectRepository(session, user)
    return {
        "user": user,
        "p1": (await projects.add(name="Main")).id,
        "p2": (await projects.add(name="Side")).id,
    }


async def create(client: httpx.AsyncClient, project: uuid.UUID, **body: Any) -> dict[str, Any]:
    response = await client.post(f"/api/v1/projects/{project}/memory", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def error(response: httpx.Response) -> dict[str, Any]:
    return response.json()["error"]


# ---- CRUD -----------------------------------------------------------------------------------


async def test_crud_for_each_kind(session: AsyncSession, gateway: Gateway, owner: dict) -> None:
    async with api_client(session, gateway, owner["user"]) as client:
        req = await create(client, owner["p1"], kind="requirement", title="Runs offline",
                           priority="must")  # fmt: skip
        dec = await create(client, owner["p1"], kind="decision", title="Use PostgreSQL",
                           body="PostgreSQL 16", why="pgvector", alternatives="MySQL")  # fmt: skip
        task = await create(client, owner["p1"], kind="task", title="Write schema",
                            priority="high")  # fmt: skip

        assert (req["status"], req["priority"]) == ("draft", "must")
        assert (dec["status"], dec["why"], dec["alternatives"]) == ("accepted", "pgvector", "MySQL")
        assert dec["decided_at"] is not None  # created already decided
        assert (task["status"], task["is_blocked"]) == ("todo", False)
        assert req["is_blocked"] is None  # only tasks

        got = (await client.get(f"/api/v1/memory/{dec['id']}")).json()
        assert got == dec

        # Partial PATCH: only `status` changes.
        patched = await client.patch(f"/api/v1/memory/{req['id']}", json={"status": "approved"})
        assert patched.status_code == 200
        body = patched.json()
        assert body["status"] == "approved" and body["title"] == "Runs offline"
        assert body["priority"] == "must" and "updated_at" in body

        # null clears an optional text field.
        cleared = await client.patch(f"/api/v1/memory/{dec['id']}", json={"alternatives": None})
        assert cleared.json()["alternatives"] is None and cleared.json()["why"] == "pgvector"

        assert (await client.delete(f"/api/v1/memory/{task['id']}")).status_code == 204
        assert (await client.get(f"/api/v1/memory/{task['id']}")).status_code == 404


async def test_empty_patch_is_422(session: AsyncSession, gateway: Gateway, owner: dict) -> None:
    async with api_client(session, gateway, owner["user"]) as client:
        item = await create(client, owner["p1"], kind="task", title="T")
        response = await client.patch(f"/api/v1/memory/{item['id']}", json={})
    assert response.status_code == 422
    assert "at least one field" in str(error(response)["details"])


@pytest.mark.parametrize(
    ("body", "field", "message"),
    [
        ({"title": "   "}, "title", "empty"),
        ({"title": ""}, "title", "empty"),
        ({"title": "x" * 201}, "title", "at most 200"),
        ({"title": "two\nlines"}, "title", "single line"),
        ({"title": "null\x00byte"}, "title", "control characters"),
        ({"title": "ok", "body": "bell\x07"}, "body", "control characters"),
        ({"title": "ok", "body": "y" * 5001}, "body", "at most 5000"),
        ({"title": "ok", "body": "  \n "}, "body", "empty"),
    ],
)
async def test_text_validation_names_the_field(
    session: AsyncSession, gateway: Gateway, owner: dict, body: dict, field: str, message: str
) -> None:
    async with api_client(session, gateway, owner["user"]) as client:
        response = await client.post(f"/api/v1/projects/{owner['p1']}/memory",
                                     json={"kind": "task", **body})  # fmt: skip
    assert response.status_code == 422
    [problem] = error(response)["details"]["errors"]
    assert problem["loc"][-1] == field
    assert message in problem["msg"]


async def test_unicode_is_kept_and_text_is_trimmed(
    session: AsyncSession, gateway: Gateway, owner: dict
) -> None:
    async with api_client(session, gateway, owner["user"]) as client:
        item = await create(
            client,
            owner["p1"],
            kind="decision",
            title="  डेटाबेस: PostgreSQL 🐘  ",
            body="कारण:\r\nfull-text\tsearch 👍",
        )
    assert item["title"] == "डेटाबेस: PostgreSQL 🐘"
    assert item["body"] == "कारण:\nfull-text\tsearch 👍"


@pytest.mark.parametrize(
    ("kind", "body", "field"),
    [
        ("task", {"status": "accepted"}, "status"),
        ("decision", {"status": "todo"}, "status"),
        ("requirement", {"priority": "high"}, "priority"),
        ("task", {"priority": "must"}, "priority"),
        ("decision", {"priority": "high"}, "priority"),
        ("task", {"why": "because"}, "why"),
        ("requirement", {"decided_at": "2026-01-01T00:00:00Z"}, "decided_at"),
    ],
)
async def test_fields_must_fit_the_kind(
    session: AsyncSession, gateway: Gateway, owner: dict, kind: str, body: dict, field: str
) -> None:
    async with api_client(session, gateway, owner["user"]) as client:
        response = await client.post(f"/api/v1/projects/{owner['p1']}/memory",
                                     json={"kind": kind, "title": "x", **body})  # fmt: skip
    assert response.status_code == 422
    assert error(response)["code"] == "invalid_field"
    assert error(response)["details"]["field"] == field


async def test_decided_at_cannot_be_in_the_future(
    session: AsyncSession, gateway: Gateway, owner: dict
) -> None:
    future = (datetime.now(UTC) + timedelta(days=1)).isoformat()
    past = (datetime.now(UTC) - timedelta(days=3)).isoformat()
    async with api_client(session, gateway, owner["user"]) as client:
        bad = await client.post(
            f"/api/v1/projects/{owner['p1']}/memory",
            json={"kind": "decision", "title": "D", "decided_at": future},
        )
        assert bad.status_code == 422
        assert "future" in error(bad)["details"]["errors"][0]["msg"]
        good = await create(client, owner["p1"], kind="decision", title="D", decided_at=past)
        assert good["decided_at"].startswith(past[:10])


# ---- lists ----------------------------------------------------------------------------------


async def test_pagination_ordering_and_filters(
    session: AsyncSession, gateway: Gateway, owner: dict
) -> None:
    async with api_client(session, gateway, owner["user"]) as client:
        made = [await create(client, owner["p1"], kind="task", title=f"T{i}") for i in range(7)]
        await client.patch(f"/api/v1/memory/{made[0]['id']}", json={"status": "done"})
        await create(client, owner["p1"], kind="decision", title="D")

        url = f"/api/v1/projects/{owner['p1']}/memory"
        first = (await client.get(url, params={"kind": "task", "limit": 3})).json()
        second = (await client.get(url, params={"kind": "task", "limit": 3, "offset": 3})).json()
        again = (await client.get(url, params={"kind": "task", "limit": 3})).json()
        assert first["total"] == 7 and first == again  # same call, same order
        ids = [i["id"] for i in first["items"] + second["items"]]
        assert len(set(ids)) == 6  # pages don't overlap

        done = (await client.get(url, params={"status": "done"})).json()
        assert [i["id"] for i in done["items"]] == [made[0]["id"]]

        too_big = await client.get(url, params={"limit": settings.memory_page_max + 1})
        assert too_big.status_code == 422 and error(too_big)["details"]["field"] == "limit"
        assert (await client.get(url, params={"limit": 0})).status_code == 422
        assert (await client.get(url, params={"offset": -1})).status_code == 422
        assert (await client.get(url, params={"status": "nonsense"})).status_code == 422


async def test_item_limit_per_kind(
    session: AsyncSession, gateway: Gateway, owner: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "memory_max_items_per_kind", 2)
    async with api_client(session, gateway, owner["user"]) as client:
        await create(client, owner["p1"], kind="task", title="1")
        await create(client, owner["p1"], kind="task", title="2")
        full = await client.post(f"/api/v1/projects/{owner['p1']}/memory",
                                 json={"kind": "task", "title": "3"})  # fmt: skip
        assert full.status_code == 409
        assert error(full)["code"] == "memory_limit_reached"
        assert "2 tasks" in error(full)["message"]
        # Other kinds and other projects have their own count.
        await create(client, owner["p1"], kind="decision", title="D")
        await create(client, owner["p2"], kind="task", title="elsewhere")


# ---- decisions and tasks through the API -----------------------------------------------------


async def test_supersede_and_dependencies_endpoints(
    session: AsyncSession, gateway: Gateway, owner: dict
) -> None:
    async with api_client(session, gateway, owner["user"]) as client:
        old = await create(client, owner["p1"], kind="decision", title="Use MySQL")
        result = await client.post(f"/api/v1/memory/{old['id']}/supersede",
                                   json={"decision": {"title": "Use PostgreSQL"}})  # fmt: skip
        assert result.status_code == 201
        body = result.json()
        assert body["superseded"]["status"] == "superseded"
        assert body["by"]["supersedes_ids"] == [old["id"]]
        both = await client.post(f"/api/v1/memory/{old['id']}/supersede",
                                 json={"decision": {"title": "x"}, "by_id": old["id"]})  # fmt: skip
        assert both.status_code == 422

        a = await create(client, owner["p1"], kind="task", title="A")
        b = await create(client, owner["p1"], kind="task", title="B")
        linked = await client.post(f"/api/v1/memory/{a['id']}/dependencies",
                                   json={"depends_on_id": b["id"]})  # fmt: skip
        assert linked.json()["depends_on_ids"] == [b["id"]] and linked.json()["is_blocked"]
        cycle = await client.post(f"/api/v1/memory/{b['id']}/dependencies",
                                  json={"depends_on_id": a["id"]})  # fmt: skip
        assert cycle.status_code == 409 and error(cycle)["code"] == "dependency_cycle"
        url = f"/api/v1/memory/{a['id']}/dependencies/{b['id']}"
        assert (await client.delete(url)).status_code == 204
        assert (await client.delete(url)).status_code == 404


async def test_deleting_a_project_removes_its_memory(
    session: AsyncSession, gateway: Gateway, owner: dict
) -> None:
    async with api_client(session, gateway, owner["user"]) as client:
        a = await create(client, owner["p1"], kind="task", title="A")
        b = await create(client, owner["p1"], kind="task", title="B")
        await client.post(f"/api/v1/memory/{a['id']}/dependencies", json={"depends_on_id": b["id"]})
        keep = await create(client, owner["p2"], kind="task", title="other project")
    await ProjectRepository(session, owner["user"]).delete(owner["p1"])
    session.expunge_all()
    left = (await session.execute(select(MemoryItem.id))).scalars().all()
    assert set(left) == {uuid.UUID(keep["id"])}
    assert (await session.execute(select(MemoryDependency))).scalars().all() == []


# ---- isolation ------------------------------------------------------------------------------


async def test_user_and_project_isolation_on_every_endpoint(
    session: AsyncSession, gateway: Gateway, owner: dict
) -> None:
    async with api_client(session, gateway, owner["user"]) as client:
        dec = await create(client, owner["p1"], kind="decision", title="Secret decision")
        t1 = await create(client, owner["p1"], kind="task", title="T1")
        t2 = await create(client, owner["p1"], kind="task", title="T2")
        await client.post(
            f"/api/v1/memory/{t1['id']}/dependencies", json={"depends_on_id": t2["id"]}
        )
        side = await create(client, owner["p2"], kind="task", title="Side task")

        # Same user, other project: links across projects are refused as not found.
        cross = await client.post(f"/api/v1/memory/{t1['id']}/dependencies",
                                  json={"depends_on_id": side["id"]})  # fmt: skip
        assert cross.status_code == 404
        p2_dec = await create(client, owner["p2"], kind="decision", title="P2")
        cross_sup = await client.post(f"/api/v1/memory/{dec['id']}/supersede",
                                      json={"by_id": p2_dec["id"]})  # fmt: skip
        assert cross_sup.status_code == 404
        p2_items = (await client.get(f"/api/v1/projects/{owner['p2']}/memory")).json()["items"]
        assert dec["id"] not in [i["id"] for i in p2_items]

    intruder = await make_user(session, "Intruder")
    async with api_client(session, gateway, intruder) as client:
        calls = [
            client.get(f"/api/v1/projects/{owner['p1']}/memory"),
            client.post(
                f"/api/v1/projects/{owner['p1']}/memory", json={"kind": "task", "title": "x"}
            ),
            client.get(f"/api/v1/memory/{dec['id']}"),
            client.patch(f"/api/v1/memory/{dec['id']}", json={"title": "mine"}),
            client.delete(f"/api/v1/memory/{dec['id']}"),
            client.post(f"/api/v1/memory/{dec['id']}/supersede", json={"decision": {"title": "x"}}),
            client.post(
                f"/api/v1/memory/{t1['id']}/dependencies", json={"depends_on_id": t2["id"]}
            ),
            client.delete(f"/api/v1/memory/{t1['id']}/dependencies/{t2['id']}"),
        ]
        for call in calls:
            response = await call
            assert response.status_code == 404, response.request.url
            assert "Secret decision" not in response.text

    async with api_client(session, gateway, owner["user"]) as client:
        still = (await client.get(f"/api/v1/memory/{dec['id']}")).json()
    assert still["title"] == "Secret decision" and still["status"] == "accepted"


async def test_logs_hold_ids_and_counts_never_text(
    session: AsyncSession, gateway: Gateway, owner: dict, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.DEBUG):
        async with api_client(session, gateway, owner["user"]) as client:
            item = await create(client, owner["p1"], kind="decision", title="CODENAME-OSPREY",
                                body="BODY-SECRET", why="WHY-SECRET")  # fmt: skip
            await client.patch(f"/api/v1/memory/{item['id']}", json={"title": "CODENAME-HERON"})
            await client.post(f"/api/v1/memory/{item['id']}/supersede",
                              json={"decision": {"title": "CODENAME-KITE"}})  # fmt: skip
    assert item["id"] in caplog.text  # ids are logged
    for secret in ("OSPREY", "HERON", "KITE", "BODY-SECRET", "WHY-SECRET"):
        assert secret not in caplog.text
