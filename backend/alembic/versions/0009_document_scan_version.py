"""The secret rules version each document was checked with.

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-20

- documents.scan_version: secret_scan.RULES_VERSION when the content was last checked. Rows
  from before this migration are NULL, so the next index run reads and checks every indexed
  file again (no embedding call unless the content changed).
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0009"
down_revision: str | Sequence[str] | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("scan_version", sa.SmallInteger(), nullable=True))


def downgrade() -> None:
    op.drop_column("documents", "scan_version")
