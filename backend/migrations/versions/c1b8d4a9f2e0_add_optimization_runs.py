"""add optimization runs

Revision ID: c1b8d4a9f2e0
Revises: 7f31c2a6e9b4
Create Date: 2026-05-19 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c1b8d4a9f2e0"
down_revision: str | Sequence[str] | None = "7f31c2a6e9b4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

portable_json = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")


def upgrade() -> None:
    op.create_table(
        "optimization_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("form_id", sa.String(length=128), nullable=False),
        sa.Column("form_version", sa.String(length=64), nullable=False),
        sa.Column("config_json", portable_json, nullable=False),
        sa.Column("split_json", portable_json, nullable=False),
        sa.Column("seed_candidate_json", portable_json, nullable=True),
        sa.Column("best_candidate_json", portable_json, nullable=True),
        sa.Column("metrics_json", portable_json, nullable=True),
        sa.Column("artifacts_json", portable_json, nullable=True),
        sa.Column("token_usage_json", portable_json, nullable=True),
        sa.Column("total_count", sa.Integer(), nullable=False),
        sa.Column("train_count", sa.Integer(), nullable=False),
        sa.Column("val_count", sa.Integer(), nullable=False),
        sa.Column("test_count", sa.Integer(), nullable=False),
        sa.Column("best_score", sa.Float(), nullable=True),
        sa.Column("original_score", sa.Float(), nullable=True),
        sa.Column("total_metric_calls", sa.Integer(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_optimization_runs")),
    )
    with op.batch_alter_table("optimization_runs", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_optimization_runs_form_id"), ["form_id"])
        batch_op.create_index(batch_op.f("ix_optimization_runs_form_version"), ["form_version"])
        batch_op.create_index(batch_op.f("ix_optimization_runs_name"), ["name"])
        batch_op.create_index(batch_op.f("ix_optimization_runs_status"), ["status"])

    op.create_table(
        "optimization_candidates",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("candidate_index", sa.Integer(), nullable=False),
        sa.Column("parent_indices_json", portable_json, nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("candidate_json", portable_json, nullable=False),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("metrics_json", portable_json, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["optimization_runs.id"],
            name=op.f("fk_optimization_candidates_run_id_optimization_runs"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_optimization_candidates")),
    )
    with op.batch_alter_table("optimization_candidates", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_optimization_candidates_candidate_index"),
            ["candidate_index"],
        )
        batch_op.create_index(batch_op.f("ix_optimization_candidates_run_id"), ["run_id"])
        batch_op.create_index(batch_op.f("ix_optimization_candidates_status"), ["status"])

    op.create_table(
        "optimization_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("payload_json", portable_json, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["optimization_runs.id"],
            name=op.f("fk_optimization_events_run_id_optimization_runs"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_optimization_events")),
    )
    with op.batch_alter_table("optimization_events", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_optimization_events_event_type"), ["event_type"])
        batch_op.create_index(batch_op.f("ix_optimization_events_run_id"), ["run_id"])
        batch_op.create_index(batch_op.f("ix_optimization_events_sequence"), ["sequence"])


def downgrade() -> None:
    with op.batch_alter_table("optimization_events", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_optimization_events_sequence"))
        batch_op.drop_index(batch_op.f("ix_optimization_events_run_id"))
        batch_op.drop_index(batch_op.f("ix_optimization_events_event_type"))
    op.drop_table("optimization_events")

    with op.batch_alter_table("optimization_candidates", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_optimization_candidates_status"))
        batch_op.drop_index(batch_op.f("ix_optimization_candidates_run_id"))
        batch_op.drop_index(batch_op.f("ix_optimization_candidates_candidate_index"))
    op.drop_table("optimization_candidates")

    with op.batch_alter_table("optimization_runs", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_optimization_runs_status"))
        batch_op.drop_index(batch_op.f("ix_optimization_runs_name"))
        batch_op.drop_index(batch_op.f("ix_optimization_runs_form_version"))
        batch_op.drop_index(batch_op.f("ix_optimization_runs_form_id"))
    op.drop_table("optimization_runs")
