"""Project profile facts: the columns the facts collector fills.

Revision ID: 0011
Revises: 0010
Create Date: 2026-11-21

project_profiles existed since 0001 (languages, dependencies, markers, index_run_id) but no
code wrote it. This adds:
- manifests, frameworks, commands, layout, entry_points (JSONB lists; every item has a
  `source` path), and built_at (when the facts were collected).
The 0001 columns keep their names; their list items now hold objects with a `source` too.

Downgrade drops the six new columns, and the facts stored in them are lost. Rows and the 0001
columns stay. The facts are rebuilt by the next successful index run after an upgrade.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0011"
down_revision: str | Sequence[str] | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_LISTS = ("manifests", "frameworks", "commands", "layout", "entry_points")


def upgrade() -> None:
    for name in _LISTS:
        op.add_column(
            "project_profiles",
            sa.Column(name, postgresql.JSONB(), server_default="[]", nullable=False),
        )
    op.add_column(
        "project_profiles", sa.Column("built_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("project_profiles", "built_at")
    for name in reversed(_LISTS):
        op.drop_column("project_profiles", name)
