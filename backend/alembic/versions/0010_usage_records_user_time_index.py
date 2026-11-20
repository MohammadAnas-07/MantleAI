"""An index for one user's newest usage rows.

Revision ID: 0010
Revises: 0009
Create Date: 2026-11-20

- ix_usage_records_user_id_created_at (user_id, created_at, id): the activity log polls the
  newest calls of a user every 10 s, and EXPLAIN on 40,000 rows showed a scan and a sort.
  Built CONCURRENTLY, so a large table stays writable while it builds; that can't run inside a
  transaction, hence the autocommit block. Downgrade drops only the index; no data is lost.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0010"
down_revision: str | Sequence[str] | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

INDEX = "ix_usage_records_user_id_created_at"


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.create_index(
            INDEX,
            "usage_records",
            ["user_id", "created_at", "id"],
            postgresql_concurrently=True,
            if_not_exists=True,
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.drop_index(INDEX, table_name="usage_records", postgresql_concurrently=True,
                      if_exists=True)  # fmt: skip
