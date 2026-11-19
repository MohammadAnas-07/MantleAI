"""A safe summary of the provider's error on usage rows.

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-19

- usage_records.error_detail: sanitized structured fields of the provider's error payload
  (HTTP status, provider status and code, quota id, retry delay). Never free text.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0007"
down_revision: str | Sequence[str] | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("usage_records", sa.Column("error_detail", sa.String(255), nullable=True))


def downgrade() -> None:
    op.drop_column("usage_records", "error_detail")
