"""Project indexing: job states and counters, skipped files, segment metadata, full-text search.

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-18

- index_runs: statuses queued | running | succeeded | failed | cancelled (`done` becomes
  `succeeded`), counters, estimate, skip report, cancel request, snapshots of the embedding
  model and root path. A partial unique index allows one queued or running job per project.
- documents: skipped files are rows too (status + skip_reason); mtime for the fast change check;
  content_hash is null until every segment is stored.
- chunks: language, type, symbol, content hash, search_text and a generated tsvector with a GIN
  index ('simple' config: no stemming, no stop words, works for identifiers). The unique
  (document_id, ordinal) constraint goes: during a run old and new segments of a changed file
  exist side by side until the file is finished.
- The HNSW index from 0001 is checked and created if it is missing.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0005"
down_revision: str | Sequence[str] | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_JSON_EMPTY = sa.text("'{}'::jsonb")


def upgrade() -> None:
    # index_runs
    op.execute("UPDATE index_runs SET status = 'succeeded' WHERE status = 'done'")
    for column in (
        sa.Column("files_unchanged", sa.Integer(), server_default="0", nullable=False),
        sa.Column("tokens", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("cost_estimate_usd", sa.Numeric(12, 6), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancel_requested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("force", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("embedding_model", sa.String(200), nullable=True),
        sa.Column("root_path", sa.Text(), nullable=True),
        sa.Column("estimate", postgresql.JSONB(), server_default=_JSON_EMPTY, nullable=False),
        sa.Column("skip_report", postgresql.JSONB(), server_default=_JSON_EMPTY, nullable=False),
    ):
        op.add_column("index_runs", column)
    op.create_index(
        "uq_index_runs_project_id_active",
        "index_runs",
        ["project_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('queued', 'running')"),
    )

    # documents
    op.add_column(
        "documents",
        sa.Column("status", sa.String(32), server_default="indexed", nullable=False),
    )
    op.add_column("documents", sa.Column("skip_reason", sa.String(64), nullable=True))
    op.add_column("documents", sa.Column("mtime_ns", sa.BigInteger(), nullable=True))
    op.add_column(
        "documents", sa.Column("line_count", sa.Integer(), server_default="0", nullable=False)
    )
    op.add_column("documents", sa.Column("parse_fallback", sa.String(32), nullable=True))
    op.add_column("documents", sa.Column("embedding_model", sa.String(200), nullable=True))
    op.alter_column("documents", "content_hash", existing_type=sa.String(64), nullable=True)

    # chunks
    op.drop_constraint("uq_chunks_document_id_ordinal", "chunks", type_="unique")
    op.add_column("chunks", sa.Column("language", sa.String(50), nullable=True))
    op.add_column(
        "chunks", sa.Column("chunk_type", sa.String(32), server_default="lines", nullable=False)
    )
    op.add_column("chunks", sa.Column("symbol", sa.Text(), nullable=True))
    op.add_column(
        "chunks", sa.Column("content_hash", sa.String(64), server_default="", nullable=False)
    )
    op.add_column("chunks", sa.Column("search_text", sa.Text(), server_default="", nullable=False))
    op.add_column(
        "chunks",
        sa.Column(
            "search_tsv",
            postgresql.TSVECTOR(),
            sa.Computed("to_tsvector('simple', search_text)", persisted=True),
            nullable=True,
        ),
    )
    op.create_index("ix_chunks_search_tsv", "chunks", ["search_tsv"], postgresql_using="gin")
    op.create_index(
        "ix_chunks_project_id_embedding_model", "chunks", ["project_id", "embedding_model"]
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_chunks_embedding_hnsw ON chunks "
        "USING hnsw (embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    op.drop_index("ix_chunks_project_id_embedding_model", table_name="chunks")
    op.drop_index("ix_chunks_search_tsv", table_name="chunks")
    for name in ("search_tsv", "search_text", "content_hash", "symbol", "chunk_type", "language"):
        op.drop_column("chunks", name)
    # Old and new segments of one file may share an ordinal; keep the newest of each.
    op.execute(
        """
        DELETE FROM chunks AS c USING chunks AS newer
        WHERE c.document_id = newer.document_id AND c.ordinal = newer.ordinal
          AND (c.created_at, c.id) < (newer.created_at, newer.id)
        """
    )
    op.create_unique_constraint(
        "uq_chunks_document_id_ordinal", "chunks", ["document_id", "ordinal"]
    )

    # Skipped and unfinished files had no row before this revision.
    op.execute("DELETE FROM documents WHERE status <> 'indexed' OR content_hash IS NULL")
    op.alter_column("documents", "content_hash", existing_type=sa.String(64), nullable=False)
    for name in ("embedding_model", "parse_fallback", "line_count", "mtime_ns", "skip_reason",
                 "status"):  # fmt: skip
        op.drop_column("documents", name)

    op.drop_index("uq_index_runs_project_id_active", table_name="index_runs")
    for name in ("skip_report", "estimate", "root_path", "embedding_model", "force",
                 "cancel_requested_at", "started_at", "cost_estimate_usd", "tokens",
                 "files_unchanged"):  # fmt: skip
        op.drop_column("index_runs", name)
    op.execute("UPDATE index_runs SET status = 'done' WHERE status = 'succeeded'")
    op.execute("UPDATE index_runs SET status = 'failed' WHERE status = 'queued'")
