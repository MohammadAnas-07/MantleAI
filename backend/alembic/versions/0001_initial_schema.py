"""Initial schema: pgvector extension and every v0.1 table.

Revision ID: 0001
Revises:
Create Date: 2026-11-17

Enums are plain VARCHAR(32) columns (no PostgreSQL enum types, no CHECK constraints), so
adding a value needs no migration. The default local user is created by `python -m app.db.seed`,
not here.
"""

from collections.abc import Sequence

import pgvector.sqlalchemy
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Dimension of chunks.embedding, frozen at the value of settings.embedding_dimensions when this
# migration was written. Migrations must not change after they are merged, so changing
# EMBEDDING_DIMENSIONS needs a NEW migration that alters the column and rebuilds the HNSW index,
# and every project must then be re-indexed. tests/test_migrations.py fails if the database
# and the setting disagree.
EMBEDDING_DIMENSIONS = 1536


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "model_configs",
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("litellm_model", sa.String(length=200), nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("context_window", sa.Integer(), nullable=False),
        sa.Column("max_output_tokens", sa.Integer(), nullable=True),
        sa.Column("embedding_dimensions", sa.Integer(), nullable=True),
        sa.Column("input_cost_per_mtok", sa.Numeric(precision=12, scale=6), nullable=True),
        sa.Column("output_cost_per_mtok", sa.Numeric(precision=12, scale=6), nullable=True),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_model_configs")),
        sa.UniqueConstraint("litellm_model", name=op.f("uq_model_configs_litellm_model")),
    )
    op.create_table(
        "users",
        sa.Column("display_name", sa.String(length=200), nullable=False),
        sa.Column(
            "is_local_default", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
    )
    op.create_table(
        "audit_events",
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("entity_type", sa.String(length=50), nullable=True),
        sa.Column("entity_id", sa.UUID(), nullable=True),
        sa.Column(
            "details",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_audit_events_user_id"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_events")),
    )
    op.create_index(op.f("ix_audit_events_user_id"), "audit_events", ["user_id"], unique=False)
    op.create_table(
        "projects",
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("root_path", sa.Text(), nullable=True),
        sa.Column("default_model_id", sa.UUID(), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["default_model_id"],
            ["model_configs.id"],
            name=op.f("fk_projects_default_model_id"),
            ondelete="SET NULL",
            initially="DEFERRED",
            deferrable=True,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_projects_user_id"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_projects")),
    )
    op.create_index(
        op.f("ix_projects_default_model_id"), "projects", ["default_model_id"], unique=False
    )
    op.create_index(op.f("ix_projects_user_id"), "projects", ["user_id"], unique=False)
    op.create_table(
        "provider_credentials",
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("label", sa.String(length=100), server_default="", nullable=False),
        sa.Column("encrypted_key", sa.LargeBinary(), nullable=False),
        sa.Column("key_hint", sa.String(length=4), nullable=False),
        sa.Column("last_tested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_test_ok", sa.Boolean(), nullable=True),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_provider_credentials_user_id"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_provider_credentials")),
    )
    op.create_index(
        op.f("ix_provider_credentials_user_id"), "provider_credentials", ["user_id"], unique=False
    )
    op.create_table(
        "user_model_settings",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("utility_model_id", sa.UUID(), nullable=True),
        sa.Column("embedding_model_id", sa.UUID(), nullable=True),
        sa.Column(
            "background_summary_enabled",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["embedding_model_id"],
            ["model_configs.id"],
            name=op.f("fk_user_model_settings_embedding_model_id"),
            ondelete="SET NULL",
            initially="DEFERRED",
            deferrable=True,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_user_model_settings_user_id"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["utility_model_id"],
            ["model_configs.id"],
            name=op.f("fk_user_model_settings_utility_model_id"),
            ondelete="SET NULL",
            initially="DEFERRED",
            deferrable=True,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_model_settings")),
        sa.UniqueConstraint("user_id", name=op.f("uq_user_model_settings_user_id")),
    )
    op.create_index(
        op.f("ix_user_model_settings_embedding_model_id"),
        "user_model_settings",
        ["embedding_model_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_user_model_settings_utility_model_id"),
        "user_model_settings",
        ["utility_model_id"],
        unique=False,
    )
    op.create_table(
        "conversations",
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("title", sa.String(length=300), server_default="", nullable=False),
        sa.Column("current_model_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["current_model_id"],
            ["model_configs.id"],
            name=op.f("fk_conversations_current_model_id"),
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_conversations_project_id"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_conversations_user_id"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_conversations")),
    )
    op.create_index(
        op.f("ix_conversations_current_model_id"),
        "conversations",
        ["current_model_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_conversations_project_id"), "conversations", ["project_id"], unique=False
    )
    op.create_index(op.f("ix_conversations_user_id"), "conversations", ["user_id"], unique=False)
    op.create_table(
        "index_runs",
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("files_seen", sa.Integer(), server_default="0", nullable=False),
        sa.Column("files_indexed", sa.Integer(), server_default="0", nullable=False),
        sa.Column("files_skipped", sa.Integer(), server_default="0", nullable=False),
        sa.Column("chunks_created", sa.Integer(), server_default="0", nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("embedding_model_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["embedding_model_id"],
            ["model_configs.id"],
            name=op.f("fk_index_runs_embedding_model_id"),
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_index_runs_project_id"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_index_runs_user_id"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_index_runs")),
    )
    op.create_index(
        op.f("ix_index_runs_embedding_model_id"), "index_runs", ["embedding_model_id"], unique=False
    )
    op.create_index(op.f("ix_index_runs_project_id"), "index_runs", ["project_id"], unique=False)
    op.create_index(op.f("ix_index_runs_user_id"), "index_runs", ["user_id"], unique=False)
    op.create_table(
        "workflow_runs",
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("current_stage_key", sa.String(length=50), nullable=True),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_workflow_runs_project_id"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_workflow_runs_user_id"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_workflow_runs")),
    )
    op.create_index(
        op.f("ix_workflow_runs_project_id"), "workflow_runs", ["project_id"], unique=False
    )
    op.create_index(op.f("ix_workflow_runs_user_id"), "workflow_runs", ["user_id"], unique=False)
    op.create_table(
        "documents",
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("language", sa.String(length=50), nullable=True),
        sa.Column("last_index_run_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["last_index_run_id"], ["index_runs.id"], name=op.f("fk_documents_last_index_run_id")
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_documents_project_id"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_documents_user_id"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_documents")),
        sa.UniqueConstraint("project_id", "path", name=op.f("uq_documents_project_id_path")),
    )
    op.create_index(
        op.f("ix_documents_last_index_run_id"), "documents", ["last_index_run_id"], unique=False
    )
    op.create_index(op.f("ix_documents_project_id"), "documents", ["project_id"], unique=False)
    op.create_index(op.f("ix_documents_user_id"), "documents", ["user_id"], unique=False)
    op.create_table(
        "messages",
        sa.Column("conversation_id", sa.UUID(), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column(
            "content", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False
        ),
        sa.Column("model_id", sa.UUID(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("token_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            name=op.f("fk_messages_conversation_id"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["model_id"], ["model_configs.id"], name=op.f("fk_messages_model_id")
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_messages_user_id"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_messages")),
    )
    op.create_index(
        op.f("ix_messages_conversation_id"), "messages", ["conversation_id"], unique=False
    )
    op.create_index(
        "ix_messages_conversation_id_created_at",
        "messages",
        ["conversation_id", "created_at"],
        unique=False,
    )
    op.create_index(op.f("ix_messages_model_id"), "messages", ["model_id"], unique=False)
    op.create_index(op.f("ix_messages_user_id"), "messages", ["user_id"], unique=False)
    op.create_table(
        "project_profiles",
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column(
            "languages",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "dependencies",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
        sa.Column(
            "markers", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False
        ),
        sa.Column("index_run_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["index_run_id"], ["index_runs.id"], name=op.f("fk_project_profiles_index_run_id")
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_project_profiles_project_id"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_project_profiles_user_id"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_project_profiles")),
        sa.UniqueConstraint("project_id", name=op.f("uq_project_profiles_project_id")),
    )
    op.create_index(
        op.f("ix_project_profiles_index_run_id"), "project_profiles", ["index_run_id"], unique=False
    )
    op.create_index(
        op.f("ix_project_profiles_user_id"), "project_profiles", ["user_id"], unique=False
    )
    op.create_table(
        "stage_states",
        sa.Column("workflow_run_id", sa.UUID(), nullable=False),
        sa.Column("stage_key", sa.String(length=50), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("output", sa.Text(), nullable=True),
        sa.Column("decision_note", sa.Text(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_stage_states_user_id"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["workflow_run_id"],
            ["workflow_runs.id"],
            name=op.f("fk_stage_states_workflow_run_id"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_stage_states")),
        sa.UniqueConstraint(
            "workflow_run_id", "stage_key", name=op.f("uq_stage_states_workflow_run_id_stage_key")
        ),
    )
    op.create_index(op.f("ix_stage_states_user_id"), "stage_states", ["user_id"], unique=False)
    op.create_index(
        op.f("ix_stage_states_workflow_run_id"), "stage_states", ["workflow_run_id"], unique=False
    )
    op.create_table(
        "agent_runs",
        sa.Column("stage_state_id", sa.UUID(), nullable=False),
        sa.Column("agent", sa.String(length=32), nullable=False),
        sa.Column("model_id", sa.UUID(), nullable=False),
        sa.Column("input_summary", sa.Text(), nullable=True),
        sa.Column("output", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["model_id"], ["model_configs.id"], name=op.f("fk_agent_runs_model_id")
        ),
        sa.ForeignKeyConstraint(
            ["stage_state_id"],
            ["stage_states.id"],
            name=op.f("fk_agent_runs_stage_state_id"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_agent_runs_user_id"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_agent_runs")),
    )
    op.create_index(op.f("ix_agent_runs_model_id"), "agent_runs", ["model_id"], unique=False)
    op.create_index(
        op.f("ix_agent_runs_stage_state_id"), "agent_runs", ["stage_state_id"], unique=False
    )
    op.create_index(op.f("ix_agent_runs_user_id"), "agent_runs", ["user_id"], unique=False)
    op.create_table(
        "chunks",
        sa.Column("document_id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("start_line", sa.Integer(), nullable=False),
        sa.Column("end_line", sa.Integer(), nullable=False),
        sa.Column("token_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "embedding", pgvector.sqlalchemy.vector.VECTOR(dim=EMBEDDING_DIMENSIONS), nullable=False
        ),
        sa.Column("embedding_model", sa.String(length=200), nullable=False),
        sa.Column("embedding_dimensions", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name=op.f("fk_chunks_document_id"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], name=op.f("fk_chunks_project_id"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_chunks_user_id"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_chunks")),
        sa.UniqueConstraint("document_id", "ordinal", name=op.f("uq_chunks_document_id_ordinal")),
    )
    op.create_index(op.f("ix_chunks_document_id"), "chunks", ["document_id"], unique=False)
    op.create_index(
        "ix_chunks_embedding_hnsw",
        "chunks",
        ["embedding"],
        unique=False,
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )
    op.create_index(op.f("ix_chunks_project_id"), "chunks", ["project_id"], unique=False)
    op.create_index(op.f("ix_chunks_user_id"), "chunks", ["user_id"], unique=False)
    op.create_table(
        "conversation_summaries",
        sa.Column("conversation_id", sa.UUID(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("up_to_message_id", sa.UUID(), nullable=False),
        sa.Column("model_id", sa.UUID(), nullable=False),
        sa.Column("built_at", sa.String(length=32), nullable=False),
        sa.Column("token_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            name=op.f("fk_conversation_summaries_conversation_id"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["model_id"], ["model_configs.id"], name=op.f("fk_conversation_summaries_model_id")
        ),
        sa.ForeignKeyConstraint(
            ["up_to_message_id"],
            ["messages.id"],
            name=op.f("fk_conversation_summaries_up_to_message_id"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_conversation_summaries_user_id"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_conversation_summaries")),
    )
    op.create_index(
        op.f("ix_conversation_summaries_conversation_id"),
        "conversation_summaries",
        ["conversation_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_conversation_summaries_model_id"),
        "conversation_summaries",
        ["model_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_conversation_summaries_up_to_message_id"),
        "conversation_summaries",
        ["up_to_message_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_conversation_summaries_user_id"),
        "conversation_summaries",
        ["user_id"],
        unique=False,
    )
    op.create_table(
        "message_contexts",
        sa.Column("message_id", sa.UUID(), nullable=False),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("source_id", sa.UUID(), nullable=False),
        sa.Column("score", sa.Double(), nullable=True),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["message_id"],
            ["messages.id"],
            name=op.f("fk_message_contexts_message_id"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_message_contexts_user_id"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_message_contexts")),
    )
    op.create_index(
        op.f("ix_message_contexts_message_id"), "message_contexts", ["message_id"], unique=False
    )
    op.create_index(
        op.f("ix_message_contexts_user_id"), "message_contexts", ["user_id"], unique=False
    )
    op.create_table(
        "teaching_notes",
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("concept", sa.String(length=200), nullable=False),
        sa.Column("what", sa.Text(), nullable=False),
        sa.Column("why_here", sa.Text(), nullable=False),
        sa.Column("how", sa.Text(), nullable=False),
        sa.Column("source_message_id", sa.UUID(), nullable=True),
        sa.Column("stage_key", sa.String(length=50), nullable=True),
        sa.Column("model_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["model_id"], ["model_configs.id"], name=op.f("fk_teaching_notes_model_id")
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_teaching_notes_project_id"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_message_id"],
            ["messages.id"],
            name=op.f("fk_teaching_notes_source_message_id"),
            ondelete="SET NULL",
            initially="DEFERRED",
            deferrable=True,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_teaching_notes_user_id"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_teaching_notes")),
    )
    op.create_index(
        op.f("ix_teaching_notes_model_id"), "teaching_notes", ["model_id"], unique=False
    )
    op.create_index(
        op.f("ix_teaching_notes_project_id"), "teaching_notes", ["project_id"], unique=False
    )
    op.create_index(
        op.f("ix_teaching_notes_source_message_id"),
        "teaching_notes",
        ["source_message_id"],
        unique=False,
    )
    op.create_index(op.f("ix_teaching_notes_user_id"), "teaching_notes", ["user_id"], unique=False)
    op.create_table(
        "concept_suggestions",
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("rule_id", sa.String(length=100), nullable=False),
        sa.Column("concept", sa.String(length=200), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("teaching_note_id", sa.UUID(), nullable=True),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_concept_suggestions_project_id"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["teaching_note_id"],
            ["teaching_notes.id"],
            name=op.f("fk_concept_suggestions_teaching_note_id"),
            ondelete="SET NULL",
            initially="DEFERRED",
            deferrable=True,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_concept_suggestions_user_id"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_concept_suggestions")),
        sa.UniqueConstraint(
            "project_id", "rule_id", name=op.f("uq_concept_suggestions_project_id_rule_id")
        ),
    )
    op.create_index(
        op.f("ix_concept_suggestions_project_id"),
        "concept_suggestions",
        ["project_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_concept_suggestions_teaching_note_id"),
        "concept_suggestions",
        ["teaching_note_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_concept_suggestions_user_id"), "concept_suggestions", ["user_id"], unique=False
    )
    op.create_table(
        "context_handoffs",
        sa.Column("conversation_id", sa.UUID(), nullable=False),
        sa.Column("from_model_id", sa.UUID(), nullable=False),
        sa.Column("to_model_id", sa.UUID(), nullable=False),
        sa.Column("reason", sa.String(length=32), nullable=False),
        sa.Column("conversation_summary_id", sa.UUID(), nullable=True),
        sa.Column("first_raw_message_id", sa.UUID(), nullable=False),
        sa.Column("tokens_before", sa.Integer(), server_default="0", nullable=False),
        sa.Column("tokens_after", sa.Integer(), server_default="0", nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            name=op.f("fk_context_handoffs_conversation_id"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["conversation_summary_id"],
            ["conversation_summaries.id"],
            name=op.f("fk_context_handoffs_conversation_summary_id"),
            ondelete="SET NULL",
            initially="DEFERRED",
            deferrable=True,
        ),
        sa.ForeignKeyConstraint(
            ["first_raw_message_id"],
            ["messages.id"],
            name=op.f("fk_context_handoffs_first_raw_message_id"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["from_model_id"], ["model_configs.id"], name=op.f("fk_context_handoffs_from_model_id")
        ),
        sa.ForeignKeyConstraint(
            ["to_model_id"], ["model_configs.id"], name=op.f("fk_context_handoffs_to_model_id")
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_context_handoffs_user_id"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_context_handoffs")),
    )
    op.create_index(
        op.f("ix_context_handoffs_conversation_id"),
        "context_handoffs",
        ["conversation_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_context_handoffs_conversation_summary_id"),
        "context_handoffs",
        ["conversation_summary_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_context_handoffs_first_raw_message_id"),
        "context_handoffs",
        ["first_raw_message_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_context_handoffs_from_model_id"),
        "context_handoffs",
        ["from_model_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_context_handoffs_to_model_id"), "context_handoffs", ["to_model_id"], unique=False
    )
    op.create_index(
        op.f("ix_context_handoffs_user_id"), "context_handoffs", ["user_id"], unique=False
    )
    op.create_table(
        "memory_items",
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("body", sa.Text(), server_default="", nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("priority", sa.String(length=32), nullable=True),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("source_message_id", sa.UUID(), nullable=True),
        sa.Column("source_agent_run_id", sa.UUID(), nullable=True),
        sa.Column("stage_key", sa.String(length=50), nullable=True),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_memory_items_project_id"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["source_agent_run_id"],
            ["agent_runs.id"],
            name=op.f("fk_memory_items_source_agent_run_id"),
            ondelete="SET NULL",
            initially="DEFERRED",
            deferrable=True,
        ),
        sa.ForeignKeyConstraint(
            ["source_message_id"],
            ["messages.id"],
            name=op.f("fk_memory_items_source_message_id"),
            ondelete="SET NULL",
            initially="DEFERRED",
            deferrable=True,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_memory_items_user_id"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_memory_items")),
    )
    op.create_index(
        op.f("ix_memory_items_project_id"), "memory_items", ["project_id"], unique=False
    )
    op.create_index(
        op.f("ix_memory_items_source_agent_run_id"),
        "memory_items",
        ["source_agent_run_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_memory_items_source_message_id"),
        "memory_items",
        ["source_message_id"],
        unique=False,
    )
    op.create_index(op.f("ix_memory_items_user_id"), "memory_items", ["user_id"], unique=False)
    op.create_table(
        "usage_records",
        sa.Column("model_id", sa.UUID(), nullable=False),
        sa.Column("purpose", sa.String(length=32), nullable=False),
        sa.Column("trigger", sa.String(length=32), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=True),
        sa.Column("conversation_id", sa.UUID(), nullable=True),
        sa.Column("message_id", sa.UUID(), nullable=True),
        sa.Column("agent_run_id", sa.UUID(), nullable=True),
        sa.Column("input_tokens", sa.Integer(), server_default="0", nullable=False),
        sa.Column("output_tokens", sa.Integer(), server_default="0", nullable=False),
        sa.Column("cost_usd", sa.Numeric(precision=12, scale=6), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["agent_run_id"],
            ["agent_runs.id"],
            name=op.f("fk_usage_records_agent_run_id"),
            ondelete="SET NULL",
            initially="DEFERRED",
            deferrable=True,
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            name=op.f("fk_usage_records_conversation_id"),
            ondelete="SET NULL",
            initially="DEFERRED",
            deferrable=True,
        ),
        sa.ForeignKeyConstraint(
            ["message_id"],
            ["messages.id"],
            name=op.f("fk_usage_records_message_id"),
            ondelete="SET NULL",
            initially="DEFERRED",
            deferrable=True,
        ),
        sa.ForeignKeyConstraint(
            ["model_id"], ["model_configs.id"], name=op.f("fk_usage_records_model_id")
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_usage_records_project_id"),
            ondelete="SET NULL",
            initially="DEFERRED",
            deferrable=True,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_usage_records_user_id"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_usage_records")),
    )
    op.create_index(
        op.f("ix_usage_records_agent_run_id"), "usage_records", ["agent_run_id"], unique=False
    )
    op.create_index(
        op.f("ix_usage_records_conversation_id"), "usage_records", ["conversation_id"], unique=False
    )
    op.create_index(
        op.f("ix_usage_records_message_id"), "usage_records", ["message_id"], unique=False
    )
    op.create_index(op.f("ix_usage_records_model_id"), "usage_records", ["model_id"], unique=False)
    op.create_index(
        op.f("ix_usage_records_project_id"), "usage_records", ["project_id"], unique=False
    )
    op.create_index(op.f("ix_usage_records_user_id"), "usage_records", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_usage_records_user_id"), table_name="usage_records")
    op.drop_index(op.f("ix_usage_records_project_id"), table_name="usage_records")
    op.drop_index(op.f("ix_usage_records_model_id"), table_name="usage_records")
    op.drop_index(op.f("ix_usage_records_message_id"), table_name="usage_records")
    op.drop_index(op.f("ix_usage_records_conversation_id"), table_name="usage_records")
    op.drop_index(op.f("ix_usage_records_agent_run_id"), table_name="usage_records")
    op.drop_table("usage_records")
    op.drop_index(op.f("ix_memory_items_user_id"), table_name="memory_items")
    op.drop_index(op.f("ix_memory_items_source_message_id"), table_name="memory_items")
    op.drop_index(op.f("ix_memory_items_source_agent_run_id"), table_name="memory_items")
    op.drop_index(op.f("ix_memory_items_project_id"), table_name="memory_items")
    op.drop_table("memory_items")
    op.drop_index(op.f("ix_context_handoffs_user_id"), table_name="context_handoffs")
    op.drop_index(op.f("ix_context_handoffs_to_model_id"), table_name="context_handoffs")
    op.drop_index(op.f("ix_context_handoffs_from_model_id"), table_name="context_handoffs")
    op.drop_index(op.f("ix_context_handoffs_first_raw_message_id"), table_name="context_handoffs")
    op.drop_index(
        op.f("ix_context_handoffs_conversation_summary_id"), table_name="context_handoffs"
    )
    op.drop_index(op.f("ix_context_handoffs_conversation_id"), table_name="context_handoffs")
    op.drop_table("context_handoffs")
    op.drop_index(op.f("ix_concept_suggestions_user_id"), table_name="concept_suggestions")
    op.drop_index(op.f("ix_concept_suggestions_teaching_note_id"), table_name="concept_suggestions")
    op.drop_index(op.f("ix_concept_suggestions_project_id"), table_name="concept_suggestions")
    op.drop_table("concept_suggestions")
    op.drop_index(op.f("ix_teaching_notes_user_id"), table_name="teaching_notes")
    op.drop_index(op.f("ix_teaching_notes_source_message_id"), table_name="teaching_notes")
    op.drop_index(op.f("ix_teaching_notes_project_id"), table_name="teaching_notes")
    op.drop_index(op.f("ix_teaching_notes_model_id"), table_name="teaching_notes")
    op.drop_table("teaching_notes")
    op.drop_index(op.f("ix_message_contexts_user_id"), table_name="message_contexts")
    op.drop_index(op.f("ix_message_contexts_message_id"), table_name="message_contexts")
    op.drop_table("message_contexts")
    op.drop_index(op.f("ix_conversation_summaries_user_id"), table_name="conversation_summaries")
    op.drop_index(
        op.f("ix_conversation_summaries_up_to_message_id"), table_name="conversation_summaries"
    )
    op.drop_index(op.f("ix_conversation_summaries_model_id"), table_name="conversation_summaries")
    op.drop_index(
        op.f("ix_conversation_summaries_conversation_id"), table_name="conversation_summaries"
    )
    op.drop_table("conversation_summaries")
    op.drop_index(op.f("ix_chunks_user_id"), table_name="chunks")
    op.drop_index(op.f("ix_chunks_project_id"), table_name="chunks")
    op.drop_index(
        "ix_chunks_embedding_hnsw",
        table_name="chunks",
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )
    op.drop_index(op.f("ix_chunks_document_id"), table_name="chunks")
    op.drop_table("chunks")
    op.drop_index(op.f("ix_agent_runs_user_id"), table_name="agent_runs")
    op.drop_index(op.f("ix_agent_runs_stage_state_id"), table_name="agent_runs")
    op.drop_index(op.f("ix_agent_runs_model_id"), table_name="agent_runs")
    op.drop_table("agent_runs")
    op.drop_index(op.f("ix_stage_states_workflow_run_id"), table_name="stage_states")
    op.drop_index(op.f("ix_stage_states_user_id"), table_name="stage_states")
    op.drop_table("stage_states")
    op.drop_index(op.f("ix_project_profiles_user_id"), table_name="project_profiles")
    op.drop_index(op.f("ix_project_profiles_index_run_id"), table_name="project_profiles")
    op.drop_table("project_profiles")
    op.drop_index(op.f("ix_messages_user_id"), table_name="messages")
    op.drop_index(op.f("ix_messages_model_id"), table_name="messages")
    op.drop_index("ix_messages_conversation_id_created_at", table_name="messages")
    op.drop_index(op.f("ix_messages_conversation_id"), table_name="messages")
    op.drop_table("messages")
    op.drop_index(op.f("ix_documents_user_id"), table_name="documents")
    op.drop_index(op.f("ix_documents_project_id"), table_name="documents")
    op.drop_index(op.f("ix_documents_last_index_run_id"), table_name="documents")
    op.drop_table("documents")
    op.drop_index(op.f("ix_workflow_runs_user_id"), table_name="workflow_runs")
    op.drop_index(op.f("ix_workflow_runs_project_id"), table_name="workflow_runs")
    op.drop_table("workflow_runs")
    op.drop_index(op.f("ix_index_runs_user_id"), table_name="index_runs")
    op.drop_index(op.f("ix_index_runs_project_id"), table_name="index_runs")
    op.drop_index(op.f("ix_index_runs_embedding_model_id"), table_name="index_runs")
    op.drop_table("index_runs")
    op.drop_index(op.f("ix_conversations_user_id"), table_name="conversations")
    op.drop_index(op.f("ix_conversations_project_id"), table_name="conversations")
    op.drop_index(op.f("ix_conversations_current_model_id"), table_name="conversations")
    op.drop_table("conversations")
    op.drop_index(op.f("ix_user_model_settings_utility_model_id"), table_name="user_model_settings")
    op.drop_index(
        op.f("ix_user_model_settings_embedding_model_id"), table_name="user_model_settings"
    )
    op.drop_table("user_model_settings")
    op.drop_index(op.f("ix_provider_credentials_user_id"), table_name="provider_credentials")
    op.drop_table("provider_credentials")
    op.drop_index(op.f("ix_projects_user_id"), table_name="projects")
    op.drop_index(op.f("ix_projects_default_model_id"), table_name="projects")
    op.drop_table("projects")
    op.drop_index(op.f("ix_audit_events_user_id"), table_name="audit_events")
    op.drop_table("audit_events")
    op.drop_table("users")
    op.drop_table("model_configs")
    op.execute("DROP EXTENSION IF EXISTS vector")
