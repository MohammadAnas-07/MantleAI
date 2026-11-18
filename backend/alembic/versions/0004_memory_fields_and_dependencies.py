"""Project memory: per-kind statuses, decision fields, supersede link, task dependencies.

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-18

Statuses and priorities are VARCHAR(32), so the new values need no column change. Existing rows
are mapped from the old shared values to each kind's own values. Downgrade maps them back; that
loses detail (for example deprecated and dropped both become rejected).
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0004"
down_revision: str | Sequence[str] | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# (kind, old status, new status)
_STATUS_UP = [
    ("decision", "active", "accepted"),
    ("decision", "done", "accepted"),
    ("requirement", "active", "approved"),
    ("requirement", "done", "approved"),
    ("requirement", "proposed", "draft"),
    ("requirement", "rejected", "dropped"),
    ("requirement", "superseded", "dropped"),
    ("task", "active", "todo"),
    ("task", "proposed", "todo"),
    ("task", "rejected", "done"),
    ("task", "superseded", "done"),
]
# (kind, old priority, new priority)
_PRIORITY_UP = [
    ("requirement", "high", "must"),
    ("requirement", "medium", "should"),
    ("requirement", "low", "could"),
]
_STATUS_DOWN = [
    ("accepted", "active"),
    ("deprecated", "rejected"),
    ("approved", "active"),
    ("draft", "proposed"),
    ("dropped", "rejected"),
    ("todo", "active"),
    ("in_progress", "active"),
    ("blocked", "active"),
]
_PRIORITY_DOWN = [("must", "high"), ("should", "medium"), ("could", "low")]


def upgrade() -> None:
    op.create_table(
        "memory_dependencies",
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("task_id", sa.UUID(), nullable=False),
        sa.Column("depends_on_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("task_id <> depends_on_id",
                           name=op.f("ck_memory_dependencies_not_self")),
        sa.ForeignKeyConstraint(["depends_on_id"], ["memory_items.id"],
                                name=op.f("fk_memory_dependencies_depends_on_id"),
                                ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"],
                                name=op.f("fk_memory_dependencies_project_id"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["task_id"], ["memory_items.id"],
                                name=op.f("fk_memory_dependencies_task_id"), ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"],
                                name=op.f("fk_memory_dependencies_user_id"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_memory_dependencies")),
        sa.UniqueConstraint("task_id", "depends_on_id",
                            name=op.f("uq_memory_dependencies_task_id_depends_on_id")),
    )  # fmt: skip
    for column in ("depends_on_id", "project_id", "task_id", "user_id"):
        op.create_index(
            op.f(f"ix_memory_dependencies_{column}"), "memory_dependencies", [column], unique=False
        )

    op.add_column("memory_items", sa.Column("why", sa.Text(), nullable=True))
    op.add_column("memory_items", sa.Column("alternatives", sa.Text(), nullable=True))
    op.add_column(
        "memory_items", sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("memory_items", sa.Column("superseded_by_id", sa.UUID(), nullable=True))
    op.create_index(
        op.f("ix_memory_items_superseded_by_id"), "memory_items", ["superseded_by_id"], unique=False
    )
    op.create_foreign_key(
        op.f("fk_memory_items_superseded_by_id"), "memory_items", "memory_items",
        ["superseded_by_id"], ["id"], ondelete="SET NULL", initially="DEFERRED", deferrable=True,
    )  # fmt: skip

    items = sa.table("memory_items", sa.column("kind"), sa.column("status"), sa.column("priority"))
    for kind, old, new in _STATUS_UP:
        op.execute(
            items.update().where(items.c.kind == kind, items.c.status == old).values(status=new)
        )
    for kind, old, new in _PRIORITY_UP:
        op.execute(
            items.update().where(items.c.kind == kind, items.c.priority == old).values(priority=new)
        )
    op.execute(items.update().where(items.c.kind == "decision").values(priority=None))


def downgrade() -> None:
    items = sa.table("memory_items", sa.column("status"), sa.column("priority"))
    for new, old in _STATUS_DOWN:
        op.execute(items.update().where(items.c.status == new).values(status=old))
    for new, old in _PRIORITY_DOWN:
        op.execute(items.update().where(items.c.priority == new).values(priority=old))

    op.drop_constraint(op.f("fk_memory_items_superseded_by_id"), "memory_items", type_="foreignkey")
    op.drop_index(op.f("ix_memory_items_superseded_by_id"), table_name="memory_items")
    op.drop_column("memory_items", "superseded_by_id")
    op.drop_column("memory_items", "decided_at")
    op.drop_column("memory_items", "alternatives")
    op.drop_column("memory_items", "why")
    for column in ("user_id", "task_id", "project_id", "depends_on_id"):
        op.drop_index(op.f(f"ix_memory_dependencies_{column}"), table_name="memory_dependencies")
    op.drop_table("memory_dependencies")
