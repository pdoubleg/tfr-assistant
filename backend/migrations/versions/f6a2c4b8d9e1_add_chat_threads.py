"""Add persistent chat threads.

Revision ID: f6a2c4b8d9e1
Revises: d4e8f1a2b3c4
Create Date: 2026-06-06 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "f6a2c4b8d9e1"
down_revision: str | Sequence[str] | None = "d4e8f1a2b3c4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

portable_json = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")


def upgrade() -> None:
    op.create_table(
        "chat_threads",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("title", sa.String(length=80), nullable=False),
        sa.Column("messages_json", portable_json, nullable=False),
        sa.Column("state_json", portable_json, nullable=True),
        sa.Column("component_anchor_turns_json", portable_json, nullable=False),
        sa.Column("model_name", sa.String(length=128), nullable=False),
        sa.Column("reasoning_effort", sa.String(length=24), nullable=True),
        sa.Column("artifact_session_id", sa.String(length=64), nullable=False),
        sa.Column("token_usage_json", portable_json, nullable=True),
        sa.Column("context_window", sa.Integer(), nullable=True),
        sa.Column("context_used_tokens", sa.Integer(), nullable=False),
        sa.Column("context_remaining_percent", sa.Float(), nullable=True),
        sa.Column("run_cost", sa.Float(), nullable=False),
        sa.Column("total_cost", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_chat_threads")),
    )
    with op.batch_alter_table("chat_threads", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_chat_threads_artifact_session_id"), ["artifact_session_id"]
        )
        batch_op.create_index(batch_op.f("ix_chat_threads_model_name"), ["model_name"])
        batch_op.create_index(batch_op.f("ix_chat_threads_title"), ["title"])
        batch_op.create_index(batch_op.f("ix_chat_threads_updated_at"), ["updated_at"])


def downgrade() -> None:
    with op.batch_alter_table("chat_threads", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_chat_threads_updated_at"))
        batch_op.drop_index(batch_op.f("ix_chat_threads_title"))
        batch_op.drop_index(batch_op.f("ix_chat_threads_model_name"))
        batch_op.drop_index(batch_op.f("ix_chat_threads_artifact_session_id"))
    op.drop_table("chat_threads")
