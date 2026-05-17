"""Add evaluation agreement projections.

Revision ID: 2a6f0b7c9d1e
Revises: 9800769b7b4a
Create Date: 2026-05-16 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "2a6f0b7c9d1e"
down_revision: str | Sequence[str] | None = "9800769b7b4a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("eval_runs", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "metrics_json",
                sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
                nullable=True,
            )
        )

    op.create_table(
        "eval_agreement_items",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("run_item_id", sa.String(length=36), nullable=False),
        sa.Column("case_id", sa.String(length=36), nullable=False),
        sa.Column("ground_truth_id", sa.String(length=36), nullable=False),
        sa.Column("comparison_id", sa.String(length=36), nullable=False),
        sa.Column("reference_kind", sa.String(length=16), nullable=False),
        sa.Column("level", sa.String(length=24), nullable=False),
        sa.Column("question_id", sa.String(length=64), nullable=True),
        sa.Column("subquestion_id", sa.String(length=64), nullable=True),
        sa.Column("question_text", sa.Text(), nullable=True),
        sa.Column("subquestion_text", sa.Text(), nullable=True),
        sa.Column("generated_answer", sa.Text(), nullable=True),
        sa.Column("reference_answer", sa.Text(), nullable=True),
        sa.Column("matched", sa.Boolean(), nullable=False),
        sa.Column("agreement", sa.Float(), nullable=False),
        sa.Column("generated_comment", sa.Text(), nullable=True),
        sa.Column("reference_comment", sa.Text(), nullable=True),
        sa.Column("generated_citations", sa.Text(), nullable=True),
        sa.Column("reference_citations", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["case_id"],
            ["eval_cases.id"],
            name=op.f("fk_eval_agreement_items_case_id_eval_cases"),
        ),
        sa.ForeignKeyConstraint(
            ["comparison_id"],
            ["eval_comparisons.id"],
            name=op.f("fk_eval_agreement_items_comparison_id_eval_comparisons"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["ground_truth_id"],
            ["eval_ground_truths.id"],
            name=op.f("fk_eval_agreement_items_ground_truth_id_eval_ground_truths"),
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["eval_runs.id"],
            name=op.f("fk_eval_agreement_items_run_id_eval_runs"),
        ),
        sa.ForeignKeyConstraint(
            ["run_item_id"],
            ["eval_run_items.id"],
            name=op.f("fk_eval_agreement_items_run_item_id_eval_run_items"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_eval_agreement_items")),
    )
    with op.batch_alter_table("eval_agreement_items", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_eval_agreement_items_case_id"),
            ["case_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_eval_agreement_items_comparison_id"),
            ["comparison_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_eval_agreement_items_ground_truth_id"),
            ["ground_truth_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_eval_agreement_items_level"),
            ["level"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_eval_agreement_items_matched"),
            ["matched"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_eval_agreement_items_question_id"),
            ["question_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_eval_agreement_items_reference_kind"),
            ["reference_kind"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_eval_agreement_items_run_id"),
            ["run_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_eval_agreement_items_run_item_id"),
            ["run_item_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_eval_agreement_items_subquestion_id"),
            ["subquestion_id"],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("eval_agreement_items", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_eval_agreement_items_subquestion_id"))
        batch_op.drop_index(batch_op.f("ix_eval_agreement_items_run_item_id"))
        batch_op.drop_index(batch_op.f("ix_eval_agreement_items_run_id"))
        batch_op.drop_index(batch_op.f("ix_eval_agreement_items_reference_kind"))
        batch_op.drop_index(batch_op.f("ix_eval_agreement_items_question_id"))
        batch_op.drop_index(batch_op.f("ix_eval_agreement_items_matched"))
        batch_op.drop_index(batch_op.f("ix_eval_agreement_items_level"))
        batch_op.drop_index(batch_op.f("ix_eval_agreement_items_ground_truth_id"))
        batch_op.drop_index(batch_op.f("ix_eval_agreement_items_comparison_id"))
        batch_op.drop_index(batch_op.f("ix_eval_agreement_items_case_id"))

    op.drop_table("eval_agreement_items")

    with op.batch_alter_table("eval_runs", schema=None) as batch_op:
        batch_op.drop_column("metrics_json")
