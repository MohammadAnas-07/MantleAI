"""The activity panel's query on many usage rows uses an index, not a scan and a sort (audit
A-014). Measured with EXPLAIN on generated rows in the test database (rolled back after)."""

import json
import uuid
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conversation_helpers import make_world

pytestmark = pytest.mark.db

# The query UsageRecordRepository.recent sends for GET /usage/records?since=...
RECENT = (
    "SELECT id FROM usage_records WHERE user_id = :user AND created_at >= now() - interval '1 hour'"
    " ORDER BY created_at DESC, id DESC LIMIT 200"
)


async def fill(session: AsyncSession, user_id: uuid.UUID, model_id: uuid.UUID, rows: int) -> None:
    """`rows` usage rows spread over the last 90 days, newest about now."""
    await session.execute(
        text(
            "INSERT INTO usage_records (id, user_id, model_id, purpose, trigger, status,"
            " input_tokens, output_tokens, created_at, updated_at)"
            " SELECT gen_random_uuid(), :user, :model, 'chat', 'user', 'success', 10, 5,"
            " now() - (n * interval '3 minutes'), now()"
            " FROM generate_series(1, :rows) AS n"
        ),
        {"user": user_id, "model": model_id, "rows": rows},
    )


def plan_nodes(plan: dict[str, Any]) -> list[dict[str, Any]]:
    out = [plan]
    for child in plan.get("Plans", []):
        out += plan_nodes(child)
    return out


async def test_recent_usage_uses_the_user_and_time_index(session: AsyncSession) -> None:
    mine = await make_world(session, "Busy")
    other = await make_world(session, "Other")
    await fill(session, mine.user_id, mine.id("small"), 30_000)
    await fill(session, other.user_id, other.id("small"), 10_000)
    await session.execute(text("ANALYZE usage_records"))
    raw = await session.scalar(text("EXPLAIN (FORMAT JSON) " + RECENT), {"user": mine.user_id})
    plan = (json.loads(raw) if isinstance(raw, str) else raw)[0]["Plan"]
    nodes = plan_nodes(plan)
    used = {n.get("Index Name") for n in nodes}
    assert "ix_usage_records_user_id_created_at" in used, json.dumps(plan)[:2000]
    # Without the index: a scan of every row and a sort (cost ~1,450 on these rows). With it,
    # the planner may still sort the few rows of the last hour, which is cheap.
    assert not any(n["Node Type"] == "Seq Scan" for n in nodes), json.dumps(plan)[:2000]
    assert plan["Total Cost"] < 500, plan["Total Cost"]
