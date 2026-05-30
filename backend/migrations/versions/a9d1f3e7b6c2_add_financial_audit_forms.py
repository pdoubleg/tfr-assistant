"""Add financial audit forms and unified result projections.

Revision ID: a9d1f3e7b6c2
Revises: c1b8d4a9f2e0
Create Date: 2026-05-30 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a9d1f3e7b6c2"
down_revision: str | Sequence[str] | None = "c1b8d4a9f2e0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_table("audit_subquestion_answers")
    op.drop_table("audit_question_answers")

    with op.batch_alter_table("audit_reviews", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("form_kind", sa.String(length=24), nullable=False, server_default="standard")
        )
        batch_op.create_index(batch_op.f("ix_audit_reviews_form_kind"), ["form_kind"])

    with op.batch_alter_table("audit_result_versions", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("form_kind", sa.String(length=24), nullable=False, server_default="standard")
        )
        batch_op.add_column(
            sa.Column("rendered_text", sa.Text(), nullable=False, server_default="")
        )
        batch_op.add_column(sa.Column("compact_text", sa.Text(), nullable=False, server_default=""))
        batch_op.add_column(sa.Column("total_amount_reviewed_dollars", sa.Numeric(18, 2)))
        batch_op.add_column(sa.Column("total_overwrite_dollars", sa.Numeric(18, 2)))
        batch_op.add_column(sa.Column("total_underwrite_dollars", sa.Numeric(18, 2)))
        batch_op.add_column(sa.Column("overwrite_percent", sa.Numeric(9, 2)))
        batch_op.add_column(sa.Column("underwrite_percent", sa.Numeric(9, 2)))
        batch_op.add_column(
            sa.Column("renderer_version", sa.Integer(), nullable=False, server_default="1")
        )
        batch_op.create_index(batch_op.f("ix_audit_result_versions_form_kind"), ["form_kind"])

    op.create_table(
        "audit_result_items",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("result_version_id", sa.String(length=36), nullable=False),
        sa.Column("review_id", sa.String(length=36), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("form_kind", sa.String(length=24), nullable=False),
        sa.Column("level", sa.String(length=24), nullable=False),
        sa.Column("question_id", sa.String(length=64), nullable=False),
        sa.Column("driver_id", sa.String(length=64), nullable=True),
        sa.Column("question_text", sa.Text(), nullable=False),
        sa.Column("driver_text", sa.Text(), nullable=True),
        sa.Column("answer_text", sa.String(length=16), nullable=True),
        sa.Column("answer_bool", sa.Boolean(), nullable=True),
        sa.Column("comments", sa.Text(), nullable=True),
        sa.Column("reasoning", sa.Text(), nullable=False),
        sa.Column("citations", sa.Text(), nullable=False),
        sa.Column("direct_overwrite_dollars", sa.Numeric(18, 2), nullable=True),
        sa.Column("direct_underwrite_dollars", sa.Numeric(18, 2), nullable=True),
        sa.Column("rollup_overwrite_dollars", sa.Numeric(18, 2), nullable=True),
        sa.Column("rollup_underwrite_dollars", sa.Numeric(18, 2), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("parent_position", sa.Integer(), nullable=True),
        sa.Column("rendered_item_text", sa.Text(), nullable=False),
        sa.Column("search_text", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["result_version_id"],
            ["audit_result_versions.id"],
            name=op.f("fk_audit_result_items_result_version_id_audit_result_versions"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["review_id"],
            ["audit_reviews.id"],
            name=op.f("fk_audit_result_items_review_id_audit_reviews"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_result_items")),
    )
    with op.batch_alter_table("audit_result_items", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_audit_result_items_answer_bool"), ["answer_bool"])
        batch_op.create_index(batch_op.f("ix_audit_result_items_answer_text"), ["answer_text"])
        batch_op.create_index(batch_op.f("ix_audit_result_items_driver_id"), ["driver_id"])
        batch_op.create_index(batch_op.f("ix_audit_result_items_form_kind"), ["form_kind"])
        batch_op.create_index(batch_op.f("ix_audit_result_items_kind"), ["kind"])
        batch_op.create_index(batch_op.f("ix_audit_result_items_level"), ["level"])
        batch_op.create_index(batch_op.f("ix_audit_result_items_question_id"), ["question_id"])
        batch_op.create_index(
            batch_op.f("ix_audit_result_items_result_version_id"), ["result_version_id"]
        )
        batch_op.create_index(batch_op.f("ix_audit_result_items_review_id"), ["review_id"])

    op.create_table(
        "audit_result_texts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("result_version_id", sa.String(length=36), nullable=False),
        sa.Column("review_id", sa.String(length=36), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("form_kind", sa.String(length=24), nullable=False),
        sa.Column("form_id", sa.String(length=128), nullable=False),
        sa.Column("form_version", sa.String(length=64), nullable=False),
        sa.Column("claim_number", sa.String(length=128), nullable=False),
        sa.Column("overall_outcome", sa.String(length=32), nullable=False),
        sa.Column("rendered_text", sa.Text(), nullable=False),
        sa.Column("compact_text", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["result_version_id"],
            ["audit_result_versions.id"],
            name=op.f("fk_audit_result_texts_result_version_id_audit_result_versions"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["review_id"],
            ["audit_reviews.id"],
            name=op.f("fk_audit_result_texts_review_id_audit_reviews"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_result_texts")),
        sa.UniqueConstraint(
            "result_version_id",
            name=op.f("uq_audit_result_texts_result_version_id"),
        ),
    )
    with op.batch_alter_table("audit_result_texts", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_audit_result_texts_claim_number"), ["claim_number"])
        batch_op.create_index(batch_op.f("ix_audit_result_texts_form_id"), ["form_id"])
        batch_op.create_index(batch_op.f("ix_audit_result_texts_form_kind"), ["form_kind"])
        batch_op.create_index(batch_op.f("ix_audit_result_texts_form_version"), ["form_version"])
        batch_op.create_index(batch_op.f("ix_audit_result_texts_kind"), ["kind"])
        batch_op.create_index(
            batch_op.f("ix_audit_result_texts_overall_outcome"), ["overall_outcome"]
        )
        batch_op.create_index(
            batch_op.f("ix_audit_result_texts_result_version_id"), ["result_version_id"]
        )
        batch_op.create_index(batch_op.f("ix_audit_result_texts_review_id"), ["review_id"])

    for table_name in ("eval_datasets", "eval_runs", "eval_comparisons"):
        with op.batch_alter_table(table_name, schema=None) as batch_op:
            batch_op.add_column(
                sa.Column(
                    "form_kind",
                    sa.String(length=24),
                    nullable=False,
                    server_default="standard",
                )
            )
            batch_op.create_index(batch_op.f(f"ix_{table_name}_form_kind"), ["form_kind"])

    with op.batch_alter_table("eval_agreement_items", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("form_kind", sa.String(length=24), nullable=False, server_default="standard")
        )
        batch_op.add_column(sa.Column("generated_overwrite_dollars", sa.Numeric(18, 2)))
        batch_op.add_column(sa.Column("reference_overwrite_dollars", sa.Numeric(18, 2)))
        batch_op.add_column(sa.Column("generated_underwrite_dollars", sa.Numeric(18, 2)))
        batch_op.add_column(sa.Column("reference_underwrite_dollars", sa.Numeric(18, 2)))
        batch_op.add_column(sa.Column("overwrite_dollar_error", sa.Numeric(18, 2)))
        batch_op.add_column(sa.Column("underwrite_dollar_error", sa.Numeric(18, 2)))
        batch_op.create_index(batch_op.f("ix_eval_agreement_items_form_kind"), ["form_kind"])

    with op.batch_alter_table("optimization_runs", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("form_kind", sa.String(length=24), nullable=False, server_default="standard")
        )
        batch_op.create_index(batch_op.f("ix_optimization_runs_form_kind"), ["form_kind"])


def downgrade() -> None:
    with op.batch_alter_table("optimization_runs", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_optimization_runs_form_kind"))
        batch_op.drop_column("form_kind")

    with op.batch_alter_table("eval_agreement_items", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_eval_agreement_items_form_kind"))
        batch_op.drop_column("underwrite_dollar_error")
        batch_op.drop_column("overwrite_dollar_error")
        batch_op.drop_column("reference_underwrite_dollars")
        batch_op.drop_column("generated_underwrite_dollars")
        batch_op.drop_column("reference_overwrite_dollars")
        batch_op.drop_column("generated_overwrite_dollars")
        batch_op.drop_column("form_kind")

    for table_name in ("eval_comparisons", "eval_runs", "eval_datasets"):
        with op.batch_alter_table(table_name, schema=None) as batch_op:
            batch_op.drop_index(batch_op.f(f"ix_{table_name}_form_kind"))
            batch_op.drop_column("form_kind")

    with op.batch_alter_table("audit_result_texts", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_audit_result_texts_review_id"))
        batch_op.drop_index(batch_op.f("ix_audit_result_texts_result_version_id"))
        batch_op.drop_index(batch_op.f("ix_audit_result_texts_overall_outcome"))
        batch_op.drop_index(batch_op.f("ix_audit_result_texts_kind"))
        batch_op.drop_index(batch_op.f("ix_audit_result_texts_form_version"))
        batch_op.drop_index(batch_op.f("ix_audit_result_texts_form_kind"))
        batch_op.drop_index(batch_op.f("ix_audit_result_texts_form_id"))
        batch_op.drop_index(batch_op.f("ix_audit_result_texts_claim_number"))
    op.drop_table("audit_result_texts")

    with op.batch_alter_table("audit_result_items", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_audit_result_items_review_id"))
        batch_op.drop_index(batch_op.f("ix_audit_result_items_result_version_id"))
        batch_op.drop_index(batch_op.f("ix_audit_result_items_question_id"))
        batch_op.drop_index(batch_op.f("ix_audit_result_items_level"))
        batch_op.drop_index(batch_op.f("ix_audit_result_items_kind"))
        batch_op.drop_index(batch_op.f("ix_audit_result_items_form_kind"))
        batch_op.drop_index(batch_op.f("ix_audit_result_items_driver_id"))
        batch_op.drop_index(batch_op.f("ix_audit_result_items_answer_text"))
        batch_op.drop_index(batch_op.f("ix_audit_result_items_answer_bool"))
    op.drop_table("audit_result_items")

    with op.batch_alter_table("audit_result_versions", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_audit_result_versions_form_kind"))
        batch_op.drop_column("renderer_version")
        batch_op.drop_column("underwrite_percent")
        batch_op.drop_column("overwrite_percent")
        batch_op.drop_column("total_underwrite_dollars")
        batch_op.drop_column("total_overwrite_dollars")
        batch_op.drop_column("total_amount_reviewed_dollars")
        batch_op.drop_column("compact_text")
        batch_op.drop_column("rendered_text")
        batch_op.drop_column("form_kind")

    with op.batch_alter_table("audit_reviews", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_audit_reviews_form_kind"))
        batch_op.drop_column("form_kind")

    op.create_table(
        "audit_question_answers",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("result_version_id", sa.String(length=36), nullable=False),
        sa.Column("review_id", sa.String(length=36), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("question_id", sa.String(length=64), nullable=False),
        sa.Column("question_text", sa.Text(), nullable=False),
        sa.Column("answer", sa.String(length=8), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_question_answers")),
    )
    op.create_table(
        "audit_subquestion_answers",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("result_version_id", sa.String(length=36), nullable=False),
        sa.Column("review_id", sa.String(length=36), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("question_id", sa.String(length=64), nullable=False),
        sa.Column("subquestion_id", sa.String(length=64), nullable=False),
        sa.Column("subquestion_text", sa.Text(), nullable=False),
        sa.Column("answer", sa.Boolean(), nullable=False),
        sa.Column("reasoning", sa.Text(), nullable=False),
        sa.Column("citations", sa.Text(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_subquestion_answers")),
    )
