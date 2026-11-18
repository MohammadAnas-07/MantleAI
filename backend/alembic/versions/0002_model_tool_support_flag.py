"""Add model_configs.supports_tools.

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-18

When a model doesn't support tools, the context builder sends tool-call history as plain text.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "model_configs",
        sa.Column("supports_tools", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("model_configs", "supports_tools")
