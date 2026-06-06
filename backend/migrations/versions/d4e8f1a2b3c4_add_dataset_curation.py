"""Add dataset curation staging tables.

Revision ID: d4e8f1a2b3c4
Revises: a9d1f3e7b6c2
Create Date: 2026-05-31 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "d4e8f1a2b3c4"
down_revision: str | Sequence[str] | None = "a9d1f3e7b6c2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

portable_json = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")


def _table_names() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _has_column(table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    if table_name not in inspector.get_table_names():
        return False
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def upgrade() -> None:
    tables = _table_names()
    if "eval_cases" in tables and not _has_column("eval_cases", "metadata_json"):
        with op.batch_alter_table("eval_cases", schema=None) as batch_op:
            batch_op.add_column(sa.Column("metadata_json", portable_json, nullable=True))

    if "dataset_populations" not in tables:
        op.create_table(
            "dataset_populations",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("name", sa.String(length=120), nullable=False),
            sa.Column("description", sa.Text(), nullable=False),
            sa.Column("form_id", sa.String(length=128), nullable=False),
            sa.Column("form_version", sa.String(length=64), nullable=False),
            sa.Column("form_kind", sa.String(length=24), nullable=False),
            sa.Column("status", sa.String(length=24), nullable=False),
            sa.Column("source_config_json", portable_json, nullable=True),
            sa.Column("cluster_config_json", portable_json, nullable=True),
            sa.Column("sample_config_json", portable_json, nullable=True),
            sa.Column("published_dataset_id", sa.String(length=36), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(
                ["published_dataset_id"],
                ["eval_datasets.id"],
                name=op.f("fk_dataset_populations_published_dataset_id_eval_datasets"),
                ondelete="SET NULL",
            ),
            sa.PrimaryKeyConstraint("id", name=op.f("pk_dataset_populations")),
        )
        with op.batch_alter_table("dataset_populations", schema=None) as batch_op:
            batch_op.create_index(batch_op.f("ix_dataset_populations_form_id"), ["form_id"])
            batch_op.create_index(
                batch_op.f("ix_dataset_populations_form_kind"),
                ["form_kind"],
            )
            batch_op.create_index(
                batch_op.f("ix_dataset_populations_form_version"),
                ["form_version"],
            )
            batch_op.create_index(batch_op.f("ix_dataset_populations_name"), ["name"])
            batch_op.create_index(
                batch_op.f("ix_dataset_populations_published_dataset_id"),
                ["published_dataset_id"],
            )
            batch_op.create_index(batch_op.f("ix_dataset_populations_status"), ["status"])

    tables = _table_names()
    if "dataset_candidates" not in tables:
        op.create_table(
            "dataset_candidates",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("population_id", sa.String(length=36), nullable=False),
            sa.Column("source_kind", sa.String(length=32), nullable=False),
            sa.Column("source_key", sa.String(length=128), nullable=False),
            sa.Column("source_label", sa.String(length=160), nullable=False),
            sa.Column("source_record_id", sa.String(length=256), nullable=False),
            sa.Column("dedupe_key", sa.String(length=64), nullable=False),
            sa.Column("claim_number", sa.String(length=128), nullable=False),
            sa.Column("effective_date", sa.String(length=64), nullable=True),
            sa.Column("instructions", sa.Text(), nullable=False),
            sa.Column("input_json", portable_json, nullable=True),
            sa.Column("references_json", portable_json, nullable=False),
            sa.Column("metadata_json", portable_json, nullable=True),
            sa.Column("tags_json", portable_json, nullable=False),
            sa.Column("metrics_json", portable_json, nullable=True),
            sa.Column("included", sa.Boolean(), nullable=False),
            sa.Column("cluster_id", sa.Integer(), nullable=True),
            sa.Column("cluster_distance", sa.Float(), nullable=True),
            sa.Column("cluster_score", sa.Float(), nullable=True),
            sa.Column("cluster_metadata_json", portable_json, nullable=True),
            sa.Column("sample_reason", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(
                ["population_id"],
                ["dataset_populations.id"],
                name=op.f("fk_dataset_candidates_population_id_dataset_populations"),
                ondelete="CASCADE",
            ),
            sa.PrimaryKeyConstraint("id", name=op.f("pk_dataset_candidates")),
            sa.UniqueConstraint(
                "population_id",
                "dedupe_key",
                name="uq_dataset_candidates_population_dedupe",
            ),
        )
        with op.batch_alter_table("dataset_candidates", schema=None) as batch_op:
            batch_op.create_index(
                batch_op.f("ix_dataset_candidates_claim_number"),
                ["claim_number"],
            )
            batch_op.create_index(batch_op.f("ix_dataset_candidates_cluster_id"), ["cluster_id"])
            batch_op.create_index(batch_op.f("ix_dataset_candidates_dedupe_key"), ["dedupe_key"])
            batch_op.create_index(batch_op.f("ix_dataset_candidates_included"), ["included"])
            batch_op.create_index(
                batch_op.f("ix_dataset_candidates_population_id"),
                ["population_id"],
            )
            batch_op.create_index(
                batch_op.f("ix_dataset_candidates_source_kind"),
                ["source_kind"],
            )
            batch_op.create_index(batch_op.f("ix_dataset_candidates_source_key"), ["source_key"])
            batch_op.create_index(
                batch_op.f("ix_dataset_candidates_source_record_id"),
                ["source_record_id"],
            )


def downgrade() -> None:
    tables = _table_names()
    if "dataset_candidates" in tables:
        with op.batch_alter_table("dataset_candidates", schema=None) as batch_op:
            batch_op.drop_index(batch_op.f("ix_dataset_candidates_source_record_id"))
            batch_op.drop_index(batch_op.f("ix_dataset_candidates_source_key"))
            batch_op.drop_index(batch_op.f("ix_dataset_candidates_source_kind"))
            batch_op.drop_index(batch_op.f("ix_dataset_candidates_population_id"))
            batch_op.drop_index(batch_op.f("ix_dataset_candidates_included"))
            batch_op.drop_index(batch_op.f("ix_dataset_candidates_dedupe_key"))
            batch_op.drop_index(batch_op.f("ix_dataset_candidates_cluster_id"))
            batch_op.drop_index(batch_op.f("ix_dataset_candidates_claim_number"))
        op.drop_table("dataset_candidates")

    tables = _table_names()
    if "dataset_populations" in tables:
        with op.batch_alter_table("dataset_populations", schema=None) as batch_op:
            batch_op.drop_index(batch_op.f("ix_dataset_populations_status"))
            batch_op.drop_index(batch_op.f("ix_dataset_populations_published_dataset_id"))
            batch_op.drop_index(batch_op.f("ix_dataset_populations_name"))
            batch_op.drop_index(batch_op.f("ix_dataset_populations_form_version"))
            batch_op.drop_index(batch_op.f("ix_dataset_populations_form_kind"))
            batch_op.drop_index(batch_op.f("ix_dataset_populations_form_id"))
        op.drop_table("dataset_populations")

    if _has_column("eval_cases", "metadata_json"):
        with op.batch_alter_table("eval_cases", schema=None) as batch_op:
            batch_op.drop_column("metadata_json")
