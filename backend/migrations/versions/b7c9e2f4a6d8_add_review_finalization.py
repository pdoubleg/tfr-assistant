"""Add review finalization metadata.

Revision ID: b7c9e2f4a6d8
Revises: e3b7a9c2d4f5
Create Date: 2026-06-07 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b7c9e2f4a6d8"
down_revision: str | Sequence[str] | None = "e3b7a9c2d4f5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _table_names() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _has_column(table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    if table_name not in inspector.get_table_names():
        return False
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def upgrade() -> None:
    if "audit_reviews" not in _table_names():
        return

    with op.batch_alter_table("audit_reviews", schema=None) as batch_op:
        if not _has_column("audit_reviews", "finalized"):
            batch_op.add_column(
                sa.Column("finalized", sa.Boolean(), nullable=False, server_default=sa.false())
            )
        if not _has_column("audit_reviews", "first_finalized_at"):
            batch_op.add_column(
                sa.Column("first_finalized_at", sa.DateTime(timezone=True), nullable=True)
            )
        if not _has_column("audit_reviews", "last_finalized_at"):
            batch_op.add_column(
                sa.Column("last_finalized_at", sa.DateTime(timezone=True), nullable=True)
            )

    with op.batch_alter_table("audit_reviews", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_audit_reviews_finalized"), ["finalized"], unique=False)


def downgrade() -> None:
    if "audit_reviews" not in _table_names():
        return

    with op.batch_alter_table("audit_reviews", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_audit_reviews_finalized"))
        if _has_column("audit_reviews", "last_finalized_at"):
            batch_op.drop_column("last_finalized_at")
        if _has_column("audit_reviews", "first_finalized_at"):
            batch_op.drop_column("first_finalized_at")
        if _has_column("audit_reviews", "finalized"):
            batch_op.drop_column("finalized")
