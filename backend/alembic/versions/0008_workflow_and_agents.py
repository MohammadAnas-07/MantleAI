"""Workflow state, workflow events, agent runs and their steps.

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-19

The placeholder tables from 0001 (workflow_runs, stage_states, and agent_runs tied to a stage
state) were never written by any code. They are replaced:
- project_workflows: one row per project (current stage, statuses, checklist, version).
- workflow_events: append-only log of workflow actions; a trigger refuses UPDATE.
- agent_runs: kept as a table (memory_items and usage_records point at it), reshaped into one
  run per request with type, status, input, estimate, result and decision. Old rows can't be
  mapped to a project, so they are deleted (their references become NULL).
- agent_run_steps: one model call per row.

Downgrade restores the 0001 tables. Agent runs, steps and events are lost on downgrade.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0008"
down_revision: str | Sequence[str] | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSONB = postgresql.JSONB(astext_type=sa.Text())


def _base_columns() -> list[sa.Column]:
    return [
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
    ]  # fmt: skip


def _user_fk(table: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        ["user_id"], ["users.id"], name=f"fk_{table}_user_id", ondelete="CASCADE"
    )


def upgrade() -> None:
    op.drop_constraint("fk_agent_runs_stage_state_id", "agent_runs", type_="foreignkey")
    op.execute("DELETE FROM agent_runs")
    op.drop_column("agent_runs", "stage_state_id")
    op.drop_column("agent_runs", "agent")
    op.drop_column("agent_runs", "input_summary")
    op.drop_column("agent_runs", "output")
    op.drop_index("ix_stage_states_workflow_run_id", table_name="stage_states")
    op.drop_index("ix_stage_states_user_id", table_name="stage_states")
    op.drop_table("stage_states")
    op.drop_index("ix_workflow_runs_user_id", table_name="workflow_runs")
    op.drop_index("ix_workflow_runs_project_id", table_name="workflow_runs")
    op.drop_table("workflow_runs")

    op.create_table(
        "project_workflows",
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("current_stage_id", sa.String(50), nullable=True),
        sa.Column("stage_statuses", JSONB, server_default="{}", nullable=False),
        sa.Column("checklist", JSONB, server_default="{}", nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        *_base_columns(),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name="fk_project_workflows_project_id",
            ondelete="CASCADE",
        ),  # fmt: skip
        _user_fk("project_workflows"),
        sa.PrimaryKeyConstraint("id", name="pk_project_workflows"),
    )
    op.create_index(
        "ix_project_workflows_project_id", "project_workflows", ["project_id"], unique=True
    )
    op.create_index("ix_project_workflows_user_id", "project_workflows", ["user_id"])

    op.create_table(
        "workflow_events",
        sa.Column("seq", sa.BigInteger(), sa.Identity(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("workflow_id", sa.UUID(), nullable=False),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("stage_id", sa.String(50), nullable=True),
        sa.Column("item_id", sa.String(50), nullable=True),
        sa.Column("actor", sa.String(32), server_default="user", nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("forced", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("details", JSONB, server_default="{}", nullable=False),
        *_base_columns(),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name="fk_workflow_events_project_id",
            ondelete="CASCADE",
        ),  # fmt: skip
        sa.ForeignKeyConstraint(
            ["workflow_id"],
            ["project_workflows.id"],
            name="fk_workflow_events_workflow_id",
            ondelete="CASCADE",
        ),  # fmt: skip
        _user_fk("workflow_events"),
        sa.PrimaryKeyConstraint("id", name="pk_workflow_events"),
    )
    op.create_index("ix_workflow_events_project_id", "workflow_events", ["project_id"])
    op.create_index("ix_workflow_events_workflow_id", "workflow_events", ["workflow_id"])
    op.create_index("ix_workflow_events_user_id", "workflow_events", ["user_id"])
    op.create_index("ix_workflow_events_seq", "workflow_events", ["seq"])
    op.execute(
        """
        CREATE FUNCTION workflow_events_append_only() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'workflow_events rows are append-only';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        "CREATE TRIGGER workflow_events_no_update BEFORE UPDATE ON workflow_events "
        "FOR EACH ROW EXECUTE FUNCTION workflow_events_append_only()"
    )

    op.add_column("agent_runs", sa.Column("project_id", sa.UUID(), nullable=False))
    op.add_column("agent_runs", sa.Column("run_type", sa.String(32), nullable=False))
    op.add_column("agent_runs", sa.Column("stage_id", sa.String(50), nullable=True))
    op.add_column("agent_runs", sa.Column("prompt_version", sa.String(100), nullable=False))
    for name, default in (
        ("input", "{}"), ("estimate", "{}"), ("result", "{}"), ("warnings", "[]"),
        ("error_details", "{}"), ("saved_item_ids", "[]"),
    ):  # fmt: skip
        op.add_column("agent_runs", sa.Column(name, JSONB, server_default=default, nullable=False))
    op.add_column("agent_runs", sa.Column("error", sa.String(64), nullable=True))
    op.add_column("agent_runs", sa.Column("error_message", sa.Text(), nullable=True))
    op.add_column(
        "agent_runs", sa.Column("input_tokens", sa.Integer(), server_default="0", nullable=False)
    )
    op.add_column(
        "agent_runs", sa.Column("output_tokens", sa.Integer(), server_default="0", nullable=False)
    )
    op.add_column("agent_runs", sa.Column("cost_usd", sa.Numeric(12, 6), nullable=True))
    for name in ("cancel_requested_at", "started_at", "decided_at"):
        op.add_column("agent_runs", sa.Column(name, sa.DateTime(timezone=True), nullable=True))
    op.add_column("agent_runs", sa.Column("decision_reason", sa.Text(), nullable=True))
    op.create_foreign_key(
        "fk_agent_runs_project_id", "agent_runs", "projects", ["project_id"], ["id"],
        ondelete="CASCADE",
    )  # fmt: skip
    op.create_index("ix_agent_runs_project_id", "agent_runs", ["project_id"])
    op.create_index(
        "uq_agent_runs_project_id_active", "agent_runs", ["project_id"], unique=True,
        postgresql_where=sa.text("status IN ('queued', 'running')"),
    )  # fmt: skip

    op.create_table(
        "agent_run_steps",
        sa.Column("run_id", sa.UUID(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("agent", sa.String(32), nullable=False),
        sa.Column("prompt_version", sa.String(50), nullable=False),
        sa.Column("model_id", sa.UUID(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("input_tokens_estimate", sa.Integer(), server_default="0", nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("output", JSONB, server_default="{}", nullable=False),
        sa.Column("input_tokens", sa.Integer(), server_default="0", nullable=False),
        sa.Column("output_tokens", sa.Integer(), server_default="0", nullable=False),
        sa.Column("cost_usd", sa.Numeric(12, 6), nullable=True),
        sa.Column("latency_ms", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error", sa.String(64), nullable=True),
        *_base_columns(),
        sa.ForeignKeyConstraint(
            ["run_id"], ["agent_runs.id"], name="fk_agent_run_steps_run_id", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["model_id"], ["model_configs.id"], name="fk_agent_run_steps_model_id"
        ),
        _user_fk("agent_run_steps"),
        sa.PrimaryKeyConstraint("id", name="pk_agent_run_steps"),
    )
    op.create_index("ix_agent_run_steps_run_id", "agent_run_steps", ["run_id"])
    op.create_index("ix_agent_run_steps_model_id", "agent_run_steps", ["model_id"])
    op.create_index("ix_agent_run_steps_user_id", "agent_run_steps", ["user_id"])


def downgrade() -> None:
    op.drop_table("agent_run_steps")
    op.execute("DELETE FROM agent_runs")
    op.drop_index("uq_agent_runs_project_id_active", table_name="agent_runs")
    op.drop_index("ix_agent_runs_project_id", table_name="agent_runs")
    op.drop_constraint("fk_agent_runs_project_id", "agent_runs", type_="foreignkey")
    for name in (
        "project_id", "run_type", "stage_id", "prompt_version", "input", "estimate", "result",
        "warnings", "error_details", "saved_item_ids", "error", "error_message", "input_tokens",
        "output_tokens", "cost_usd", "cancel_requested_at", "started_at", "decided_at",
        "decision_reason",
    ):  # fmt: skip
        op.drop_column("agent_runs", name)
    op.execute("DROP TRIGGER workflow_events_no_update ON workflow_events")
    op.execute("DROP FUNCTION workflow_events_append_only()")
    op.drop_table("workflow_events")
    op.drop_table("project_workflows")

    op.create_table(
        "workflow_runs",
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("current_stage_key", sa.String(50), nullable=True),
        *_base_columns(),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name="fk_workflow_runs_project_id",
            ondelete="CASCADE",
        ),  # fmt: skip
        _user_fk("workflow_runs"),
        sa.PrimaryKeyConstraint("id", name="pk_workflow_runs"),
    )
    op.create_index("ix_workflow_runs_project_id", "workflow_runs", ["project_id"])
    op.create_index("ix_workflow_runs_user_id", "workflow_runs", ["user_id"])
    op.create_table(
        "stage_states",
        sa.Column("workflow_run_id", sa.UUID(), nullable=False),
        sa.Column("stage_key", sa.String(50), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("output", sa.Text(), nullable=True),
        sa.Column("decision_note", sa.Text(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        *_base_columns(),
        _user_fk("stage_states"),
        sa.ForeignKeyConstraint(
            ["workflow_run_id"],
            ["workflow_runs.id"],
            name="fk_stage_states_workflow_run_id",
            ondelete="CASCADE",
        ),  # fmt: skip
        sa.PrimaryKeyConstraint("id", name="pk_stage_states"),
        sa.UniqueConstraint(
            "workflow_run_id", "stage_key", name="uq_stage_states_workflow_run_id_stage_key"
        ),
    )
    op.create_index("ix_stage_states_user_id", "stage_states", ["user_id"])
    op.create_index("ix_stage_states_workflow_run_id", "stage_states", ["workflow_run_id"])
    op.add_column("agent_runs", sa.Column("stage_state_id", sa.UUID(), nullable=False))
    op.add_column("agent_runs", sa.Column("agent", sa.String(32), nullable=False))
    op.add_column("agent_runs", sa.Column("input_summary", sa.Text(), nullable=True))
    op.add_column("agent_runs", sa.Column("output", sa.Text(), nullable=True))
    op.create_foreign_key(
        "fk_agent_runs_stage_state_id", "agent_runs", "stage_states", ["stage_state_id"], ["id"],
        ondelete="CASCADE",
    )  # fmt: skip
    # 0001's downgrade drops this index by name.
    op.create_index("ix_agent_runs_stage_state_id", "agent_runs", ["stage_state_id"])
