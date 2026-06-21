"""add audit observability tables

Revision ID: 91c3b6d0e4f2
Revises: b7c9e2f4a6d8
Create Date: 2026-06-21 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "91c3b6d0e4f2"
down_revision: str | Sequence[str] | None = "b7c9e2f4a6d8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

portable_json = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")


def _table_names() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _create_indexes(table: str, columns: list[str]) -> None:
    with op.batch_alter_table(table, schema=None) as batch_op:
        for column in columns:
            batch_op.create_index(batch_op.f(f"ix_{table}_{column}"), [column])


def _create_postgres_indexes() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    statements = [
        """
        CREATE INDEX IF NOT EXISTS ix_audit_spans_attributes_gin
        ON audit_spans USING gin (attributes_json)
        """,
        """
        CREATE INDEX IF NOT EXISTS ix_audit_spans_raw_gin
        ON audit_spans USING gin (raw_span_json)
        """,
        """
        CREATE INDEX IF NOT EXISTS ix_audit_artifacts_metadata_gin
        ON audit_artifacts USING gin (metadata_json)
        """,
        """
        CREATE INDEX IF NOT EXISTS ix_audit_artifacts_content_fts
        ON audit_artifacts USING gin (
            to_tsvector(
                'english',
                coalesce(content_text, '') || ' ' || coalesce(content_preview, '')
            )
        )
        """,
        """
        CREATE INDEX IF NOT EXISTS ix_audit_spans_attr_operation
        ON audit_spans ((attributes_json ->> 'gen_ai.operation.name'))
        """,
        """
        CREATE INDEX IF NOT EXISTS ix_audit_spans_attr_delegates_to
        ON audit_spans ((attributes_json ->> 'audit.delegates_to_agent'))
        """,
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'pg_trgm') THEN
                CREATE INDEX IF NOT EXISTS ix_audit_artifacts_content_trgm
                ON audit_artifacts USING gin (content_text gin_trgm_ops);
            END IF;
        END $$;
        """,
    ]
    for statement in statements:
        op.execute(sa.text(statement))


def upgrade() -> None:
    tables = _table_names()
    if "audit_traces" not in tables:
        op.create_table(
            "audit_traces",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("trace_id", sa.String(length=32), nullable=False),
            sa.Column("audit_run_id", sa.String(length=36), nullable=True),
            sa.Column("review_id", sa.String(length=36), nullable=True),
            sa.Column("source", sa.String(length=32), nullable=False),
            sa.Column("source_run_id", sa.String(length=64), nullable=True),
            sa.Column("batch_id", sa.String(length=36), nullable=True),
            sa.Column("eval_run_id", sa.String(length=36), nullable=True),
            sa.Column("eval_dataset_id", sa.String(length=36), nullable=True),
            sa.Column("optimization_run_id", sa.String(length=36), nullable=True),
            sa.Column("case_id", sa.String(length=64), nullable=True),
            sa.Column("claim_number", sa.String(length=128), nullable=False),
            sa.Column("form_id", sa.String(length=128), nullable=False),
            sa.Column("form_version", sa.String(length=64), nullable=False),
            sa.Column("form_kind", sa.String(length=24), nullable=False),
            sa.Column("tenant_id", sa.String(length=64), nullable=True),
            sa.Column("user_id", sa.String(length=64), nullable=True),
            sa.Column("status_code", sa.String(length=24), nullable=False),
            sa.Column("error_type", sa.String(length=256), nullable=True),
            sa.Column("span_count", sa.Integer(), nullable=False),
            sa.Column("error_count", sa.Integer(), nullable=False),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("duration_ms", sa.Integer(), nullable=True),
            sa.Column("agent_names_json", portable_json, nullable=False),
            sa.Column("model_names_json", portable_json, nullable=False),
            sa.Column("tool_names_json", portable_json, nullable=False),
            sa.Column("input_tokens", sa.Integer(), nullable=False),
            sa.Column("output_tokens", sa.Integer(), nullable=False),
            sa.Column("total_tokens", sa.Integer(), nullable=False),
            sa.Column("estimated_cost_usd", sa.Float(), nullable=True),
            sa.Column("attributes_json", portable_json, nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(
                ["review_id"],
                ["audit_reviews.id"],
                name=op.f("fk_audit_traces_review_id_audit_reviews"),
                ondelete="SET NULL",
            ),
            sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_traces")),
            sa.UniqueConstraint("trace_id", name=op.f("uq_audit_traces_trace_id")),
        )
        _create_indexes(
            "audit_traces",
            [
                "trace_id",
                "audit_run_id",
                "review_id",
                "source",
                "source_run_id",
                "batch_id",
                "eval_run_id",
                "eval_dataset_id",
                "optimization_run_id",
                "case_id",
                "claim_number",
                "form_id",
                "form_version",
                "form_kind",
                "tenant_id",
                "user_id",
                "status_code",
                "error_type",
                "started_at",
            ],
        )

    if "audit_spans" not in tables:
        op.create_table(
            "audit_spans",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("trace_id", sa.String(length=32), nullable=False),
            sa.Column("span_id", sa.String(length=16), nullable=False),
            sa.Column("parent_span_id", sa.String(length=16), nullable=True),
            sa.Column("name", sa.String(length=512), nullable=False),
            sa.Column("kind", sa.String(length=32), nullable=False),
            sa.Column("span_type", sa.String(length=32), nullable=False),
            sa.Column("status_code", sa.String(length=24), nullable=False),
            sa.Column("error_type", sa.String(length=256), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("agent_name", sa.String(length=256), nullable=False),
            sa.Column("model_name", sa.String(length=256), nullable=False),
            sa.Column("provider_name", sa.String(length=128), nullable=False),
            sa.Column("tool_name", sa.String(length=256), nullable=False),
            sa.Column("audit_run_id", sa.String(length=36), nullable=True),
            sa.Column("review_id", sa.String(length=36), nullable=True),
            sa.Column("source", sa.String(length=32), nullable=False),
            sa.Column("source_run_id", sa.String(length=64), nullable=True),
            sa.Column("batch_id", sa.String(length=36), nullable=True),
            sa.Column("eval_run_id", sa.String(length=36), nullable=True),
            sa.Column("eval_dataset_id", sa.String(length=36), nullable=True),
            sa.Column("optimization_run_id", sa.String(length=36), nullable=True),
            sa.Column("case_id", sa.String(length=64), nullable=True),
            sa.Column("claim_number", sa.String(length=128), nullable=False),
            sa.Column("form_id", sa.String(length=128), nullable=False),
            sa.Column("form_version", sa.String(length=64), nullable=False),
            sa.Column("form_kind", sa.String(length=24), nullable=False),
            sa.Column("tenant_id", sa.String(length=64), nullable=True),
            sa.Column("user_id", sa.String(length=64), nullable=True),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("duration_ms", sa.Integer(), nullable=True),
            sa.Column("input_tokens", sa.Integer(), nullable=False),
            sa.Column("output_tokens", sa.Integer(), nullable=False),
            sa.Column("total_tokens", sa.Integer(), nullable=False),
            sa.Column("estimated_cost_usd", sa.Float(), nullable=True),
            sa.Column("attributes_json", portable_json, nullable=False),
            sa.Column("resource_json", portable_json, nullable=False),
            sa.Column("raw_span_json", portable_json, nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(
                ["trace_id"],
                ["audit_traces.trace_id"],
                name=op.f("fk_audit_spans_trace_id_audit_traces"),
                ondelete="CASCADE",
            ),
            sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_spans")),
            sa.UniqueConstraint("trace_id", "span_id", name="uq_audit_spans_trace_span"),
        )
        _create_indexes(
            "audit_spans",
            [
                "trace_id",
                "span_id",
                "parent_span_id",
                "name",
                "span_type",
                "status_code",
                "error_type",
                "agent_name",
                "model_name",
                "provider_name",
                "tool_name",
                "audit_run_id",
                "review_id",
                "source",
                "source_run_id",
                "batch_id",
                "eval_run_id",
                "eval_dataset_id",
                "optimization_run_id",
                "case_id",
                "claim_number",
                "form_id",
                "form_version",
                "tenant_id",
                "user_id",
                "started_at",
            ],
        )
        op.create_index(
            "ix_audit_spans_trace_parent_started",
            "audit_spans",
            ["trace_id", "parent_span_id", "started_at"],
        )

    if "audit_span_events" not in tables:
        op.create_table(
            "audit_span_events",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("trace_id", sa.String(length=32), nullable=False),
            sa.Column("span_id", sa.String(length=16), nullable=False),
            sa.Column("event_index", sa.Integer(), nullable=False),
            sa.Column("name", sa.String(length=256), nullable=False),
            sa.Column("event_time", sa.DateTime(timezone=True), nullable=True),
            sa.Column("exception_type", sa.String(length=256), nullable=True),
            sa.Column("exception_message", sa.Text(), nullable=True),
            sa.Column("attributes_json", portable_json, nullable=False),
            sa.Column("raw_event_json", portable_json, nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_span_events")),
            sa.UniqueConstraint(
                "trace_id",
                "span_id",
                "event_index",
                name="uq_audit_span_events_trace_span_index",
            ),
        )
        _create_indexes(
            "audit_span_events",
            ["trace_id", "span_id", "name", "exception_type"],
        )

    if "audit_artifacts" not in tables:
        op.create_table(
            "audit_artifacts",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("trace_id", sa.String(length=32), nullable=False),
            sa.Column("span_id", sa.String(length=16), nullable=True),
            sa.Column("audit_run_id", sa.String(length=36), nullable=True),
            sa.Column("review_id", sa.String(length=36), nullable=True),
            sa.Column("source", sa.String(length=32), nullable=False),
            sa.Column("source_run_id", sa.String(length=64), nullable=True),
            sa.Column("batch_id", sa.String(length=36), nullable=True),
            sa.Column("eval_run_id", sa.String(length=36), nullable=True),
            sa.Column("optimization_run_id", sa.String(length=36), nullable=True),
            sa.Column("case_id", sa.String(length=64), nullable=True),
            sa.Column("claim_number", sa.String(length=128), nullable=False),
            sa.Column("artifact_type", sa.String(length=64), nullable=False),
            sa.Column("artifact_key", sa.String(length=256), nullable=False),
            sa.Column("name", sa.String(length=256), nullable=False),
            sa.Column("content_format", sa.String(length=64), nullable=False),
            sa.Column("content_preview", sa.Text(), nullable=False),
            sa.Column("content_text", sa.Text(), nullable=True),
            sa.Column("content_sha256", sa.String(length=64), nullable=False),
            sa.Column("content_size", sa.Integer(), nullable=False),
            sa.Column("blob_uri", sa.String(length=512), nullable=True),
            sa.Column("redaction_state", sa.String(length=32), nullable=False),
            sa.Column("metadata_json", portable_json, nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(
                ["trace_id"],
                ["audit_traces.trace_id"],
                name=op.f("fk_audit_artifacts_trace_id_audit_traces"),
                ondelete="CASCADE",
            ),
            sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_artifacts")),
            sa.UniqueConstraint(
                "trace_id",
                "span_id",
                "artifact_key",
                "content_sha256",
                name="uq_audit_artifacts_span_key_hash",
            ),
        )
        _create_indexes(
            "audit_artifacts",
            [
                "trace_id",
                "span_id",
                "audit_run_id",
                "review_id",
                "source",
                "source_run_id",
                "batch_id",
                "eval_run_id",
                "optimization_run_id",
                "case_id",
                "claim_number",
                "artifact_type",
                "artifact_key",
                "content_sha256",
                "redaction_state",
            ],
        )
        op.create_index(
            "ix_audit_artifacts_trace_type_created",
            "audit_artifacts",
            ["trace_id", "artifact_type", "created_at"],
        )

    if "audit_agent_delegations" not in tables:
        op.create_table(
            "audit_agent_delegations",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("trace_id", sa.String(length=32), nullable=False),
            sa.Column("parent_span_id", sa.String(length=16), nullable=True),
            sa.Column("child_span_id", sa.String(length=16), nullable=False),
            sa.Column("parent_agent_name", sa.String(length=256), nullable=False),
            sa.Column("child_agent_name", sa.String(length=256), nullable=False),
            sa.Column("tool_name", sa.String(length=256), nullable=False),
            sa.Column("confidence", sa.Float(), nullable=False),
            sa.Column("attributes_json", portable_json, nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(
                ["trace_id"],
                ["audit_traces.trace_id"],
                name=op.f("fk_audit_agent_delegations_trace_id_audit_traces"),
                ondelete="CASCADE",
            ),
            sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_agent_delegations")),
            sa.UniqueConstraint(
                "trace_id",
                "parent_span_id",
                "child_span_id",
                name="uq_audit_agent_delegations_edge",
            ),
        )
        _create_indexes(
            "audit_agent_delegations",
            ["trace_id", "parent_span_id", "child_span_id", "child_agent_name", "tool_name"],
        )

    _create_postgres_indexes()


def downgrade() -> None:
    tables = _table_names()
    for table in (
        "audit_agent_delegations",
        "audit_artifacts",
        "audit_span_events",
        "audit_spans",
        "audit_traces",
    ):
        if table in tables:
            op.drop_table(table)
