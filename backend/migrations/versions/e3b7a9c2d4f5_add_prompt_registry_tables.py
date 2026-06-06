"""Add prompt registry tables.

Revision ID: e3b7a9c2d4f5
Revises: f6a2c4b8d9e1
Create Date: 2026-06-06 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "e3b7a9c2d4f5"
down_revision: str | Sequence[str] | None = "f6a2c4b8d9e1"
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

    if "audit_batch_templates" in tables and not _has_column(
        "audit_batch_templates",
        "prompt_ref_json",
    ):
        with op.batch_alter_table("audit_batch_templates", schema=None) as batch_op:
            batch_op.add_column(sa.Column("prompt_ref_json", portable_json, nullable=True))

    if "prompt_families" not in tables:
        op.create_table(
            "prompt_families",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("form_id", sa.String(length=128), nullable=False),
            sa.Column("task", sa.String(length=64), nullable=False),
            sa.Column("prompt_kind", sa.String(length=64), nullable=False),
            sa.Column("name", sa.String(length=160), nullable=False),
            sa.Column("description", sa.Text(), nullable=False),
            sa.Column("external_registry_uri", sa.String(length=512), nullable=True),
            sa.Column("metadata_json", portable_json, nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id", name=op.f("pk_prompt_families")),
            sa.UniqueConstraint(
                "form_id",
                "task",
                "prompt_kind",
                name="uq_prompt_family_scope",
            ),
        )
        with op.batch_alter_table("prompt_families", schema=None) as batch_op:
            batch_op.create_index(batch_op.f("ix_prompt_families_form_id"), ["form_id"])
            batch_op.create_index(batch_op.f("ix_prompt_families_prompt_kind"), ["prompt_kind"])
            batch_op.create_index(batch_op.f("ix_prompt_families_task"), ["task"])

    tables = _table_names()
    if "prompt_versions" not in tables:
        op.create_table(
            "prompt_versions",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("family_id", sa.String(length=36), nullable=False),
            sa.Column("version_number", sa.Integer(), nullable=False),
            sa.Column("text", sa.Text(), nullable=False),
            sa.Column("text_hash", sa.String(length=64), nullable=False),
            sa.Column("components_json", portable_json, nullable=True),
            sa.Column("source_kind", sa.String(length=32), nullable=False),
            sa.Column("source_run_id", sa.String(length=36), nullable=True),
            sa.Column("source_candidate_index", sa.Integer(), nullable=True),
            sa.Column("source_metadata_json", portable_json, nullable=True),
            sa.Column("commit_message", sa.Text(), nullable=False),
            sa.Column("created_by", sa.String(length=120), nullable=False),
            sa.Column("metrics_json", portable_json, nullable=True),
            sa.Column("applicable_form_versions_json", portable_json, nullable=False),
            sa.Column("form_schema_fingerprint", sa.String(length=64), nullable=False),
            sa.Column("external_prompt_uri", sa.String(length=512), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(
                ["family_id"],
                ["prompt_families.id"],
                name=op.f("fk_prompt_versions_family_id_prompt_families"),
            ),
            sa.PrimaryKeyConstraint("id", name=op.f("pk_prompt_versions")),
            sa.UniqueConstraint("family_id", "version_number", name="uq_prompt_version_number"),
        )
        with op.batch_alter_table("prompt_versions", schema=None) as batch_op:
            batch_op.create_index(
                batch_op.f("ix_prompt_versions_family_id"),
                ["family_id"],
            )
            batch_op.create_index(
                batch_op.f("ix_prompt_versions_form_schema_fingerprint"),
                ["form_schema_fingerprint"],
            )
            batch_op.create_index(
                batch_op.f("ix_prompt_versions_source_kind"),
                ["source_kind"],
            )
            batch_op.create_index(
                batch_op.f("ix_prompt_versions_source_run_id"),
                ["source_run_id"],
            )
            batch_op.create_index(batch_op.f("ix_prompt_versions_text_hash"), ["text_hash"])
            batch_op.create_index(
                batch_op.f("ix_prompt_versions_version_number"),
                ["version_number"],
            )

    tables = _table_names()
    if "prompt_aliases" not in tables:
        op.create_table(
            "prompt_aliases",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("family_id", sa.String(length=36), nullable=False),
            sa.Column("alias", sa.String(length=64), nullable=False),
            sa.Column("version_id", sa.String(length=36), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(
                ["family_id"],
                ["prompt_families.id"],
                name=op.f("fk_prompt_aliases_family_id_prompt_families"),
            ),
            sa.ForeignKeyConstraint(
                ["version_id"],
                ["prompt_versions.id"],
                name=op.f("fk_prompt_aliases_version_id_prompt_versions"),
            ),
            sa.PrimaryKeyConstraint("id", name=op.f("pk_prompt_aliases")),
            sa.UniqueConstraint("family_id", "alias", name="uq_prompt_alias_name"),
        )
        with op.batch_alter_table("prompt_aliases", schema=None) as batch_op:
            batch_op.create_index(batch_op.f("ix_prompt_aliases_alias"), ["alias"])
            batch_op.create_index(batch_op.f("ix_prompt_aliases_family_id"), ["family_id"])
            batch_op.create_index(batch_op.f("ix_prompt_aliases_version_id"), ["version_id"])

    tables = _table_names()
    if "prompt_activations" not in tables:
        op.create_table(
            "prompt_activations",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("family_id", sa.String(length=36), nullable=False),
            sa.Column("version_id", sa.String(length=36), nullable=False),
            sa.Column("scope_key", sa.String(length=96), nullable=False),
            sa.Column("scope", sa.String(length=32), nullable=False),
            sa.Column("form_version", sa.String(length=64), nullable=True),
            sa.Column("activated_by", sa.String(length=120), nullable=False),
            sa.Column("notes", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(
                ["family_id"],
                ["prompt_families.id"],
                name=op.f("fk_prompt_activations_family_id_prompt_families"),
            ),
            sa.ForeignKeyConstraint(
                ["version_id"],
                ["prompt_versions.id"],
                name=op.f("fk_prompt_activations_version_id_prompt_versions"),
            ),
            sa.PrimaryKeyConstraint("id", name=op.f("pk_prompt_activations")),
            sa.UniqueConstraint("family_id", "scope_key", name="uq_prompt_activation_scope"),
        )
        with op.batch_alter_table("prompt_activations", schema=None) as batch_op:
            batch_op.create_index(
                batch_op.f("ix_prompt_activations_family_id"),
                ["family_id"],
            )
            batch_op.create_index(
                batch_op.f("ix_prompt_activations_form_version"),
                ["form_version"],
            )
            batch_op.create_index(batch_op.f("ix_prompt_activations_scope"), ["scope"])
            batch_op.create_index(batch_op.f("ix_prompt_activations_scope_key"), ["scope_key"])
            batch_op.create_index(
                batch_op.f("ix_prompt_activations_version_id"),
                ["version_id"],
            )


def downgrade() -> None:
    tables = _table_names()

    if "prompt_activations" in tables:
        with op.batch_alter_table("prompt_activations", schema=None) as batch_op:
            batch_op.drop_index(batch_op.f("ix_prompt_activations_version_id"))
            batch_op.drop_index(batch_op.f("ix_prompt_activations_scope_key"))
            batch_op.drop_index(batch_op.f("ix_prompt_activations_scope"))
            batch_op.drop_index(batch_op.f("ix_prompt_activations_form_version"))
            batch_op.drop_index(batch_op.f("ix_prompt_activations_family_id"))
        op.drop_table("prompt_activations")

    tables = _table_names()
    if "prompt_aliases" in tables:
        with op.batch_alter_table("prompt_aliases", schema=None) as batch_op:
            batch_op.drop_index(batch_op.f("ix_prompt_aliases_version_id"))
            batch_op.drop_index(batch_op.f("ix_prompt_aliases_family_id"))
            batch_op.drop_index(batch_op.f("ix_prompt_aliases_alias"))
        op.drop_table("prompt_aliases")

    tables = _table_names()
    if "prompt_versions" in tables:
        with op.batch_alter_table("prompt_versions", schema=None) as batch_op:
            batch_op.drop_index(batch_op.f("ix_prompt_versions_version_number"))
            batch_op.drop_index(batch_op.f("ix_prompt_versions_text_hash"))
            batch_op.drop_index(batch_op.f("ix_prompt_versions_source_run_id"))
            batch_op.drop_index(batch_op.f("ix_prompt_versions_source_kind"))
            batch_op.drop_index(batch_op.f("ix_prompt_versions_form_schema_fingerprint"))
            batch_op.drop_index(batch_op.f("ix_prompt_versions_family_id"))
        op.drop_table("prompt_versions")

    tables = _table_names()
    if "prompt_families" in tables:
        with op.batch_alter_table("prompt_families", schema=None) as batch_op:
            batch_op.drop_index(batch_op.f("ix_prompt_families_task"))
            batch_op.drop_index(batch_op.f("ix_prompt_families_prompt_kind"))
            batch_op.drop_index(batch_op.f("ix_prompt_families_form_id"))
        op.drop_table("prompt_families")

    if _has_column("audit_batch_templates", "prompt_ref_json"):
        with op.batch_alter_table("audit_batch_templates", schema=None) as batch_op:
            batch_op.drop_column("prompt_ref_json")
