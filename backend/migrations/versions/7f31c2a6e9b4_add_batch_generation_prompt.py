"""add batch generation prompt

Revision ID: 7f31c2a6e9b4
Revises: 2a6f0b7c9d1e
Create Date: 2026-05-18 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "7f31c2a6e9b4"
down_revision: str | Sequence[str] | None = "2a6f0b7c9d1e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("audit_batch_templates", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("generation_prompt", sa.Text(), nullable=False, server_default="")
        )
    with op.batch_alter_table("audit_batch_templates", schema=None) as batch_op:
        batch_op.alter_column("generation_prompt", server_default=None)


def downgrade() -> None:
    with op.batch_alter_table("audit_batch_templates", schema=None) as batch_op:
        batch_op.drop_column("generation_prompt")
