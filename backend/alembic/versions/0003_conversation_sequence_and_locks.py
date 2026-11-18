"""Conversation sequence numbers, job locks and the handoff note.

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-18

- messages.sequence: 1, 2, 3, ... per conversation (backfilled from created_at order).
- conversation_summaries.from_sequence / to_sequence: the messages a summary covers
  (backfilled from up_to_message_id).
- conversations.generating_since / summary_started_at: one reply and one summary job at a time.
- conversations.summary_error: the last failed summary job (rule 55).
- context_handoffs.note: the handoff note shown to the user (never sent to a model).
- context_handoffs.first_raw_message_id: now nullable (a switch with no messages carries none).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0003"
down_revision: str | Sequence[str] | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # messages.sequence
    op.add_column("messages", sa.Column("sequence", sa.Integer(), nullable=True))
    op.execute(
        """
        UPDATE messages AS m SET sequence = numbered.seq
        FROM (
            SELECT id, row_number() OVER (
                PARTITION BY conversation_id ORDER BY created_at, id
            ) AS seq
            FROM messages
        ) AS numbered
        WHERE m.id = numbered.id
        """
    )
    op.alter_column("messages", "sequence", nullable=False)
    op.create_unique_constraint(
        op.f("uq_messages_conversation_id_sequence"), "messages", ["conversation_id", "sequence"]
    )

    # conversation_summaries range
    op.add_column("conversation_summaries", sa.Column("from_sequence", sa.Integer(), nullable=True))
    op.add_column("conversation_summaries", sa.Column("to_sequence", sa.Integer(), nullable=True))
    op.execute(
        """
        UPDATE conversation_summaries AS s
        SET from_sequence = 1, to_sequence = m.sequence
        FROM messages AS m
        WHERE m.id = s.up_to_message_id
        """
    )
    op.alter_column("conversation_summaries", "from_sequence", nullable=False)
    op.alter_column("conversation_summaries", "to_sequence", nullable=False)

    # conversation locks
    op.add_column(
        "conversations", sa.Column("generating_since", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "conversations", sa.Column("summary_started_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("conversations", sa.Column("summary_error", sa.String(length=64), nullable=True))

    # handoff note, optional first raw message
    op.add_column(
        "context_handoffs",
        sa.Column(
            "note",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )
    op.alter_column("context_handoffs", "first_raw_message_id", nullable=True)
    op.drop_constraint(
        op.f("fk_context_handoffs_first_raw_message_id"), "context_handoffs", type_="foreignkey"
    )
    op.create_foreign_key(
        op.f("fk_context_handoffs_first_raw_message_id"),
        "context_handoffs",
        "messages",
        ["first_raw_message_id"],
        ["id"],
        ondelete="SET NULL",
        deferrable=True,
        initially="DEFERRED",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("fk_context_handoffs_first_raw_message_id"), "context_handoffs", type_="foreignkey"
    )
    # Handoffs that carried no message can't satisfy NOT NULL again.
    op.execute("DELETE FROM context_handoffs WHERE first_raw_message_id IS NULL")
    op.create_foreign_key(
        op.f("fk_context_handoffs_first_raw_message_id"),
        "context_handoffs",
        "messages",
        ["first_raw_message_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.alter_column("context_handoffs", "first_raw_message_id", nullable=False)
    op.drop_column("context_handoffs", "note")

    op.drop_column("conversations", "summary_error")
    op.drop_column("conversations", "summary_started_at")
    op.drop_column("conversations", "generating_since")

    op.drop_column("conversation_summaries", "to_sequence")
    op.drop_column("conversation_summaries", "from_sequence")

    op.drop_constraint(op.f("uq_messages_conversation_id_sequence"), "messages", type_="unique")
    op.drop_column("messages", "sequence")
