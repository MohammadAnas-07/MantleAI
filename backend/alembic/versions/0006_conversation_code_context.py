"""Per-conversation switch for project code context, and line ranges on message contexts.

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-18

- conversations.code_context_enabled (default true): when false, no code is retrieved.
- message_contexts.start_line / end_line: the lines of a chunk that were sent with a reply.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0006"
down_revision: str | Sequence[str] | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "conversations",
        sa.Column("code_context_enabled", sa.Boolean(), server_default=sa.true(), nullable=False),
    )
    op.add_column("message_contexts", sa.Column("start_line", sa.Integer(), nullable=True))
    op.add_column("message_contexts", sa.Column("end_line", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("message_contexts", "end_line")
    op.drop_column("message_contexts", "start_line")
    op.drop_column("conversations", "code_context_enabled")
