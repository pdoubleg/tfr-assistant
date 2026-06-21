from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON as SqlJSON,
)
from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

PortableJSON = SqlJSON().with_variant(JSONB(), "postgresql")


def utc_now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class ChatThreadORM(Base):
    __tablename__ = "chat_threads"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    title: Mapped[str] = mapped_column(String(80), default="New chat", index=True)
    messages_json: Mapped[list[dict[str, Any]]] = mapped_column(
        PortableJSON,
        default=list,
        nullable=False,
    )
    state_json: Mapped[dict[str, Any] | None] = mapped_column(PortableJSON, nullable=True)
    component_anchor_turns_json: Mapped[dict[str, int]] = mapped_column(
        PortableJSON,
        default=dict,
        nullable=False,
    )
    model_name: Mapped[str] = mapped_column(String(128), default="", index=True)
    reasoning_effort: Mapped[str | None] = mapped_column(String(24), nullable=True)
    artifact_session_id: Mapped[str] = mapped_column(String(64), default="", index=True)
    token_usage_json: Mapped[dict[str, Any] | None] = mapped_column(PortableJSON, nullable=True)
    context_window: Mapped[int | None] = mapped_column(Integer, nullable=True)
    context_used_tokens: Mapped[int] = mapped_column(Integer, default=0)
    context_remaining_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    run_cost: Mapped[float] = mapped_column(Float, default=0.0)
    total_cost: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
    )


class AuditBatchORM(Base):
    __tablename__ = "audit_batches"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    template_id: Mapped[str | None] = mapped_column(
        ForeignKey("audit_batch_templates.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    status: Mapped[str] = mapped_column(String(24), default="queued", index=True)
    source: Mapped[str] = mapped_column(String(32), default="batch")
    total_count: Mapped[int] = mapped_column(Integer, default=0)
    completed_count: Mapped[int] = mapped_column(Integer, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, default=0)
    input_json: Mapped[dict[str, Any] | None] = mapped_column(PortableJSON, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
    )

    template: Mapped["AuditBatchTemplateORM | None"] = relationship(back_populates="runs")
    reviews: Mapped[list["AuditReviewORM"]] = relationship(back_populates="batch")


class AuditBatchTemplateORM(Base):
    __tablename__ = "audit_batch_templates"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    form_id: Mapped[str] = mapped_column(String(128), index=True)
    form_version: Mapped[str] = mapped_column(String(64), index=True)
    synthetic: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    synthetic_count: Mapped[int] = mapped_column(Integer, default=0)
    input_mode: Mapped[str] = mapped_column(String(24), default="manual")
    generation_prompt: Mapped[str] = mapped_column(Text, default="")
    prompt_ref_json: Mapped[dict[str, Any] | None] = mapped_column(PortableJSON, nullable=True)
    excel_column_map: Mapped[dict[str, Any] | None] = mapped_column(PortableJSON, nullable=True)
    items_json: Mapped[list[dict[str, Any]]] = mapped_column(
        PortableJSON,
        default=list,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
    )

    runs: Mapped[list[AuditBatchORM]] = relationship(back_populates="template")


class AuditReviewORM(Base):
    __tablename__ = "audit_reviews"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    batch_id: Mapped[str | None] = mapped_column(
        ForeignKey("audit_batches.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    form_id: Mapped[str] = mapped_column(String(128), index=True)
    form_version: Mapped[str] = mapped_column(String(64), index=True)
    form_kind: Mapped[str] = mapped_column(String(24), default="standard", index=True)
    status: Mapped[str] = mapped_column(String(24), default="queued", index=True)
    source: Mapped[str] = mapped_column(String(32), default="api", index=True)
    input_json: Mapped[dict[str, Any] | None] = mapped_column(PortableJSON, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    original_result_version_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    current_user_result_version_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    finalized: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    first_finalized_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    last_finalized_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
    )

    batch: Mapped[AuditBatchORM | None] = relationship(back_populates="reviews")
    versions: Mapped[list["AuditResultVersionORM"]] = relationship(
        back_populates="review",
        cascade="all, delete-orphan",
    )


class AuditResultVersionORM(Base):
    __tablename__ = "audit_result_versions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    review_id: Mapped[str] = mapped_column(
        ForeignKey("audit_reviews.id", ondelete="CASCADE"),
        index=True,
    )
    kind: Mapped[str] = mapped_column(String(16), index=True)
    form_kind: Mapped[str] = mapped_column(String(24), default="standard", index=True)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    payload_json: Mapped[dict[str, Any]] = mapped_column(PortableJSON, nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), index=True)
    rendered_text: Mapped[str] = mapped_column(Text, default="")
    compact_text: Mapped[str] = mapped_column(Text, default="")
    total_amount_reviewed_dollars: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 2),
        nullable=True,
    )
    total_overwrite_dollars: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    total_underwrite_dollars: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    overwrite_percent: Mapped[Decimal | None] = mapped_column(Numeric(9, 2), nullable=True)
    underwrite_percent: Mapped[Decimal | None] = mapped_column(Numeric(9, 2), nullable=True)
    renderer_version: Mapped[int] = mapped_column(Integer, default=1)
    created_by: Mapped[str] = mapped_column(String(64), default="agent")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    review: Mapped[AuditReviewORM] = relationship(back_populates="versions")


class AuditResultItemORM(Base):
    __tablename__ = "audit_result_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    result_version_id: Mapped[str] = mapped_column(
        ForeignKey("audit_result_versions.id", ondelete="CASCADE"),
        index=True,
    )
    review_id: Mapped[str] = mapped_column(
        ForeignKey("audit_reviews.id", ondelete="CASCADE"),
        index=True,
    )
    kind: Mapped[str] = mapped_column(String(16), index=True)
    form_kind: Mapped[str] = mapped_column(String(24), default="standard", index=True)
    level: Mapped[str] = mapped_column(String(24), index=True)
    question_id: Mapped[str] = mapped_column(String(64), index=True)
    driver_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    question_text: Mapped[str] = mapped_column(Text)
    driver_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    answer_text: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    answer_bool: Mapped[bool | None] = mapped_column(Boolean, nullable=True, index=True)
    comments: Mapped[str | None] = mapped_column(Text, nullable=True)
    reasoning: Mapped[str] = mapped_column(Text, default="")
    citations: Mapped[str] = mapped_column(Text, default="")
    direct_overwrite_dollars: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    direct_underwrite_dollars: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    rollup_overwrite_dollars: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    rollup_underwrite_dollars: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    position: Mapped[int] = mapped_column(Integer)
    parent_position: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rendered_item_text: Mapped[str] = mapped_column(Text, default="")
    search_text: Mapped[str] = mapped_column(Text, default="")


class AuditResultTextORM(Base):
    __tablename__ = "audit_result_texts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    result_version_id: Mapped[str] = mapped_column(
        ForeignKey("audit_result_versions.id", ondelete="CASCADE"),
        unique=True,
        index=True,
    )
    review_id: Mapped[str] = mapped_column(
        ForeignKey("audit_reviews.id", ondelete="CASCADE"),
        index=True,
    )
    kind: Mapped[str] = mapped_column(String(16), index=True)
    form_kind: Mapped[str] = mapped_column(String(24), default="standard", index=True)
    form_id: Mapped[str] = mapped_column(String(128), index=True)
    form_version: Mapped[str] = mapped_column(String(64), index=True)
    claim_number: Mapped[str] = mapped_column(String(128), default="", index=True)
    overall_outcome: Mapped[str] = mapped_column(String(32), default="", index=True)
    rendered_text: Mapped[str] = mapped_column(Text, default="")
    compact_text: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class FeedbackORM(Base):
    __tablename__ = "review_feedback"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    review_id: Mapped[str] = mapped_column(
        ForeignKey("audit_reviews.id", ondelete="CASCADE"),
        index=True,
    )
    rating: Mapped[int] = mapped_column(Integer)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class EvaluationORM(Base):
    __tablename__ = "review_evaluations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    review_id: Mapped[str] = mapped_column(
        ForeignKey("audit_reviews.id", ondelete="CASCADE"),
        index=True,
    )
    evaluator: Mapped[str] = mapped_column(String(64), default="user")
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload_json: Mapped[dict[str, Any] | None] = mapped_column(PortableJSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class EvalDatasetORM(Base):
    __tablename__ = "eval_datasets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    form_id: Mapped[str] = mapped_column(String(128), index=True)
    form_version: Mapped[str] = mapped_column(String(64), index=True)
    form_kind: Mapped[str] = mapped_column(String(24), default="standard", index=True)
    source_kind: Mapped[str] = mapped_column(String(32), default="manual")
    source_metadata_json: Mapped[dict[str, Any] | None] = mapped_column(
        PortableJSON,
        nullable=True,
    )
    dataset_hash: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
    )

    cases: Mapped[list["EvalCaseORM"]] = relationship(
        back_populates="dataset",
        cascade="all, delete-orphan",
    )
    runs: Mapped[list["EvalRunORM"]] = relationship(back_populates="dataset")


class EvalCaseORM(Base):
    __tablename__ = "eval_cases"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    dataset_id: Mapped[str] = mapped_column(ForeignKey("eval_datasets.id"), index=True)
    claim_number: Mapped[str] = mapped_column(String(128), index=True)
    effective_date: Mapped[str | None] = mapped_column(String(64), nullable=True)
    instructions: Mapped[str] = mapped_column(Text, default="")
    input_json: Mapped[dict[str, Any] | None] = mapped_column(PortableJSON, nullable=True)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(PortableJSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
    )

    dataset: Mapped[EvalDatasetORM] = relationship(back_populates="cases")
    ground_truths: Mapped[list["EvalGroundTruthORM"]] = relationship(
        back_populates="case",
        cascade="all, delete-orphan",
    )
    run_items: Mapped[list["EvalRunItemORM"]] = relationship(back_populates="case")


class EvalGroundTruthORM(Base):
    __tablename__ = "eval_ground_truths"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    case_id: Mapped[str] = mapped_column(ForeignKey("eval_cases.id"), index=True)
    reference_kind: Mapped[str] = mapped_column(String(16), index=True)
    payload_json: Mapped[dict[str, Any]] = mapped_column(PortableJSON, nullable=False)
    reviewer: Mapped[str | None] = mapped_column(String(120), nullable=True)
    source_metadata_json: Mapped[dict[str, Any] | None] = mapped_column(
        PortableJSON,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    case: Mapped[EvalCaseORM] = relationship(back_populates="ground_truths")
    comparisons: Mapped[list["EvalComparisonORM"]] = relationship(back_populates="ground_truth")


class DatasetPopulationORM(Base):
    __tablename__ = "dataset_populations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    form_id: Mapped[str] = mapped_column(String(128), index=True)
    form_version: Mapped[str] = mapped_column(String(64), index=True)
    form_kind: Mapped[str] = mapped_column(String(24), default="standard", index=True)
    status: Mapped[str] = mapped_column(String(24), default="draft", index=True)
    source_config_json: Mapped[dict[str, Any] | None] = mapped_column(PortableJSON, nullable=True)
    cluster_config_json: Mapped[dict[str, Any] | None] = mapped_column(PortableJSON, nullable=True)
    sample_config_json: Mapped[dict[str, Any] | None] = mapped_column(PortableJSON, nullable=True)
    published_dataset_id: Mapped[str | None] = mapped_column(
        ForeignKey("eval_datasets.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
    )

    candidates: Mapped[list["DatasetCandidateORM"]] = relationship(
        back_populates="population",
        cascade="all, delete-orphan",
    )


class DatasetCandidateORM(Base):
    __tablename__ = "dataset_candidates"
    __table_args__ = (
        UniqueConstraint(
            "population_id",
            "dedupe_key",
            name="uq_dataset_candidates_population_dedupe",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    population_id: Mapped[str] = mapped_column(
        ForeignKey("dataset_populations.id", ondelete="CASCADE"),
        index=True,
    )
    source_kind: Mapped[str] = mapped_column(String(32), index=True)
    source_key: Mapped[str] = mapped_column(String(128), index=True)
    source_label: Mapped[str] = mapped_column(String(160), default="")
    source_record_id: Mapped[str] = mapped_column(String(256), index=True)
    dedupe_key: Mapped[str] = mapped_column(String(64), index=True)
    claim_number: Mapped[str] = mapped_column(String(128), default="", index=True)
    effective_date: Mapped[str | None] = mapped_column(String(64), nullable=True)
    instructions: Mapped[str] = mapped_column(Text, default="")
    input_json: Mapped[dict[str, Any] | None] = mapped_column(PortableJSON, nullable=True)
    references_json: Mapped[list[dict[str, Any]]] = mapped_column(
        PortableJSON,
        default=list,
        nullable=False,
    )
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(PortableJSON, nullable=True)
    tags_json: Mapped[list[str]] = mapped_column(PortableJSON, default=list, nullable=False)
    metrics_json: Mapped[dict[str, Any] | None] = mapped_column(PortableJSON, nullable=True)
    included: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    cluster_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    cluster_distance: Mapped[float | None] = mapped_column(Float, nullable=True)
    cluster_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    cluster_metadata_json: Mapped[dict[str, Any] | None] = mapped_column(
        PortableJSON,
        nullable=True,
    )
    sample_reason: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
    )

    population: Mapped[DatasetPopulationORM] = relationship(back_populates="candidates")


class EvalRunORM(Base):
    __tablename__ = "eval_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    dataset_id: Mapped[str] = mapped_column(ForeignKey("eval_datasets.id"), index=True)
    form_kind: Mapped[str] = mapped_column(String(24), default="standard", index=True)
    lineage_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    source_run_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    config_version: Mapped[int] = mapped_column(Integer, default=1)
    name: Mapped[str] = mapped_column(String(120), index=True)
    status: Mapped[str] = mapped_column(String(24), default="queued", index=True)
    model_name: Mapped[str] = mapped_column(String(128), default="")
    reference_policy: Mapped[str] = mapped_column(String(32), default="prefer_r2")
    concurrency: Mapped[int] = mapped_column(Integer, default=1)
    retry_limit: Mapped[int] = mapped_column(Integer, default=0)
    enable_mlflow: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    mlflow_run_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    total_count: Mapped[int] = mapped_column(Integer, default=0)
    completed_count: Mapped[int] = mapped_column(Integer, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, default=0)
    metrics_json: Mapped[dict[str, Any] | None] = mapped_column(PortableJSON, nullable=True)
    input_json: Mapped[dict[str, Any] | None] = mapped_column(PortableJSON, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
    )

    dataset: Mapped[EvalDatasetORM] = relationship(back_populates="runs")
    items: Mapped[list["EvalRunItemORM"]] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
    )


class EvalRunItemORM(Base):
    __tablename__ = "eval_run_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("eval_runs.id"), index=True)
    case_id: Mapped[str] = mapped_column(ForeignKey("eval_cases.id"), index=True)
    generated_review_id: Mapped[str | None] = mapped_column(
        ForeignKey("audit_reviews.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    status: Mapped[str] = mapped_column(String(24), default="queued", index=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
    )

    run: Mapped[EvalRunORM] = relationship(back_populates="items")
    case: Mapped[EvalCaseORM] = relationship(back_populates="run_items")
    comparisons: Mapped[list["EvalComparisonORM"]] = relationship(
        back_populates="run_item",
        cascade="all, delete-orphan",
    )


class EvalComparisonORM(Base):
    __tablename__ = "eval_comparisons"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("eval_runs.id"), index=True)
    run_item_id: Mapped[str] = mapped_column(ForeignKey("eval_run_items.id"), index=True)
    case_id: Mapped[str] = mapped_column(ForeignKey("eval_cases.id"), index=True)
    ground_truth_id: Mapped[str] = mapped_column(ForeignKey("eval_ground_truths.id"), index=True)
    reference_kind: Mapped[str] = mapped_column(String(16), index=True)
    form_kind: Mapped[str] = mapped_column(String(24), default="standard", index=True)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    metrics_json: Mapped[dict[str, Any]] = mapped_column(PortableJSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    run_item: Mapped[EvalRunItemORM] = relationship(back_populates="comparisons")
    ground_truth: Mapped[EvalGroundTruthORM] = relationship(back_populates="comparisons")
    agreement_items: Mapped[list["EvalAgreementItemORM"]] = relationship(
        back_populates="comparison",
        cascade="all, delete-orphan",
    )


class EvalAgreementItemORM(Base):
    __tablename__ = "eval_agreement_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("eval_runs.id"), index=True)
    run_item_id: Mapped[str] = mapped_column(ForeignKey("eval_run_items.id"), index=True)
    case_id: Mapped[str] = mapped_column(ForeignKey("eval_cases.id"), index=True)
    ground_truth_id: Mapped[str] = mapped_column(ForeignKey("eval_ground_truths.id"), index=True)
    comparison_id: Mapped[str] = mapped_column(
        ForeignKey("eval_comparisons.id", ondelete="CASCADE"),
        index=True,
    )
    reference_kind: Mapped[str] = mapped_column(String(16), index=True)
    form_kind: Mapped[str] = mapped_column(String(24), default="standard", index=True)
    level: Mapped[str] = mapped_column(String(24), index=True)
    question_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    subquestion_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    question_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    subquestion_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    generated_answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    reference_answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    matched: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    agreement: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    generated_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    reference_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    generated_citations: Mapped[str | None] = mapped_column(Text, nullable=True)
    reference_citations: Mapped[str | None] = mapped_column(Text, nullable=True)
    generated_overwrite_dollars: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 2),
        nullable=True,
    )
    reference_overwrite_dollars: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 2),
        nullable=True,
    )
    generated_underwrite_dollars: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 2),
        nullable=True,
    )
    reference_underwrite_dollars: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 2),
        nullable=True,
    )
    overwrite_dollar_error: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    underwrite_dollar_error: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    comparison: Mapped[EvalComparisonORM] = relationship(back_populates="agreement_items")


class OptimizationRunORM(Base):
    __tablename__ = "optimization_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), index=True)
    status: Mapped[str] = mapped_column(String(24), default="queued", index=True)
    form_id: Mapped[str] = mapped_column(String(128), index=True)
    form_version: Mapped[str] = mapped_column(String(64), index=True)
    form_kind: Mapped[str] = mapped_column(String(24), default="standard", index=True)
    config_json: Mapped[dict[str, Any]] = mapped_column(PortableJSON, nullable=False)
    split_json: Mapped[list[dict[str, Any]]] = mapped_column(
        PortableJSON,
        default=list,
        nullable=False,
    )
    seed_candidate_json: Mapped[dict[str, Any] | None] = mapped_column(
        PortableJSON,
        nullable=True,
    )
    best_candidate_json: Mapped[dict[str, Any] | None] = mapped_column(
        PortableJSON,
        nullable=True,
    )
    metrics_json: Mapped[dict[str, Any] | None] = mapped_column(PortableJSON, nullable=True)
    artifacts_json: Mapped[dict[str, Any] | None] = mapped_column(PortableJSON, nullable=True)
    token_usage_json: Mapped[dict[str, Any] | None] = mapped_column(PortableJSON, nullable=True)
    total_count: Mapped[int] = mapped_column(Integer, default=0)
    train_count: Mapped[int] = mapped_column(Integer, default=0)
    val_count: Mapped[int] = mapped_column(Integer, default=0)
    test_count: Mapped[int] = mapped_column(Integer, default=0)
    best_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    original_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_metric_calls: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
    )

    candidates: Mapped[list["OptimizationCandidateORM"]] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
    )
    events: Mapped[list["OptimizationEventORM"]] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
    )


class OptimizationCandidateORM(Base):
    __tablename__ = "optimization_candidates"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("optimization_runs.id"), index=True)
    candidate_index: Mapped[int] = mapped_column(Integer, index=True)
    parent_indices_json: Mapped[list[int | None]] = mapped_column(
        PortableJSON,
        default=list,
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(24), default="candidate", index=True)
    candidate_json: Mapped[dict[str, Any]] = mapped_column(PortableJSON, nullable=False)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    metrics_json: Mapped[dict[str, Any] | None] = mapped_column(PortableJSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    run: Mapped[OptimizationRunORM] = relationship(back_populates="candidates")


class OptimizationEventORM(Base):
    __tablename__ = "optimization_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("optimization_runs.id"), index=True)
    sequence: Mapped[int] = mapped_column(Integer, index=True)
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    payload_json: Mapped[dict[str, Any]] = mapped_column(PortableJSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    run: Mapped[OptimizationRunORM] = relationship(back_populates="events")


class AuditTraceORM(Base):
    __tablename__ = "audit_traces"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    trace_id: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    audit_run_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    review_id: Mapped[str | None] = mapped_column(
        ForeignKey("audit_reviews.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    source: Mapped[str] = mapped_column(String(32), default="", index=True)
    source_run_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    batch_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    eval_run_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    eval_dataset_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    optimization_run_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    case_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    claim_number: Mapped[str] = mapped_column(String(128), default="", index=True)
    form_id: Mapped[str] = mapped_column(String(128), default="", index=True)
    form_version: Mapped[str] = mapped_column(String(64), default="", index=True)
    form_kind: Mapped[str] = mapped_column(String(24), default="", index=True)
    tenant_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    user_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    status_code: Mapped[str] = mapped_column(String(24), default="UNSET", index=True)
    error_type: Mapped[str | None] = mapped_column(String(256), nullable=True, index=True)
    span_count: Mapped[int] = mapped_column(Integer, default=0)
    error_count: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    agent_names_json: Mapped[list[str]] = mapped_column(PortableJSON, default=list, nullable=False)
    model_names_json: Mapped[list[str]] = mapped_column(PortableJSON, default=list, nullable=False)
    tool_names_json: Mapped[list[str]] = mapped_column(PortableJSON, default=list, nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    estimated_cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    attributes_json: Mapped[dict[str, Any]] = mapped_column(
        PortableJSON, default=dict, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
    )

    spans: Mapped[list["AuditSpanORM"]] = relationship(back_populates="trace")
    artifacts: Mapped[list["AuditArtifactORM"]] = relationship(back_populates="trace")


class AuditSpanORM(Base):
    __tablename__ = "audit_spans"
    __table_args__ = (
        UniqueConstraint("trace_id", "span_id", name="uq_audit_spans_trace_span"),
        Index("ix_audit_spans_trace_parent_started", "trace_id", "parent_span_id", "started_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    trace_id: Mapped[str] = mapped_column(
        ForeignKey("audit_traces.trace_id", ondelete="CASCADE"),
        index=True,
    )
    span_id: Mapped[str] = mapped_column(String(16), index=True)
    parent_span_id: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(512), default="", index=True)
    kind: Mapped[str] = mapped_column(String(32), default="")
    span_type: Mapped[str] = mapped_column(String(32), default="", index=True)
    status_code: Mapped[str] = mapped_column(String(24), default="UNSET", index=True)
    error_type: Mapped[str | None] = mapped_column(String(256), nullable=True, index=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    agent_name: Mapped[str] = mapped_column(String(256), default="", index=True)
    model_name: Mapped[str] = mapped_column(String(256), default="", index=True)
    provider_name: Mapped[str] = mapped_column(String(128), default="", index=True)
    tool_name: Mapped[str] = mapped_column(String(256), default="", index=True)
    audit_run_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    review_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    source: Mapped[str] = mapped_column(String(32), default="", index=True)
    source_run_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    batch_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    eval_run_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    eval_dataset_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    optimization_run_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    case_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    claim_number: Mapped[str] = mapped_column(String(128), default="", index=True)
    form_id: Mapped[str] = mapped_column(String(128), default="", index=True)
    form_version: Mapped[str] = mapped_column(String(64), default="", index=True)
    form_kind: Mapped[str] = mapped_column(String(24), default="", index=True)
    tenant_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    user_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    estimated_cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    attributes_json: Mapped[dict[str, Any]] = mapped_column(
        PortableJSON, default=dict, nullable=False
    )
    resource_json: Mapped[dict[str, Any]] = mapped_column(
        PortableJSON, default=dict, nullable=False
    )
    raw_span_json: Mapped[dict[str, Any]] = mapped_column(
        PortableJSON, default=dict, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
    )

    trace: Mapped[AuditTraceORM] = relationship(back_populates="spans")


class AuditSpanEventORM(Base):
    __tablename__ = "audit_span_events"
    __table_args__ = (
        UniqueConstraint(
            "trace_id",
            "span_id",
            "event_index",
            name="uq_audit_span_events_trace_span_index",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    trace_id: Mapped[str] = mapped_column(String(32), index=True)
    span_id: Mapped[str] = mapped_column(String(16), index=True)
    event_index: Mapped[int] = mapped_column(Integer, default=0)
    name: Mapped[str] = mapped_column(String(256), default="", index=True)
    event_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    exception_type: Mapped[str | None] = mapped_column(String(256), nullable=True, index=True)
    exception_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    attributes_json: Mapped[dict[str, Any]] = mapped_column(
        PortableJSON, default=dict, nullable=False
    )
    raw_event_json: Mapped[dict[str, Any]] = mapped_column(
        PortableJSON, default=dict, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class AuditArtifactORM(Base):
    __tablename__ = "audit_artifacts"
    __table_args__ = (
        UniqueConstraint(
            "trace_id",
            "span_id",
            "artifact_key",
            "content_sha256",
            name="uq_audit_artifacts_span_key_hash",
        ),
        Index("ix_audit_artifacts_trace_type_created", "trace_id", "artifact_type", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    trace_id: Mapped[str] = mapped_column(
        ForeignKey("audit_traces.trace_id", ondelete="CASCADE"),
        index=True,
    )
    span_id: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    audit_run_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    review_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    source: Mapped[str] = mapped_column(String(32), default="", index=True)
    source_run_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    batch_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    eval_run_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    optimization_run_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    case_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    claim_number: Mapped[str] = mapped_column(String(128), default="", index=True)
    artifact_type: Mapped[str] = mapped_column(String(64), default="", index=True)
    artifact_key: Mapped[str] = mapped_column(String(256), default="", index=True)
    name: Mapped[str] = mapped_column(String(256), default="")
    content_format: Mapped[str] = mapped_column(String(64), default="text")
    content_preview: Mapped[str] = mapped_column(Text, default="")
    content_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_sha256: Mapped[str] = mapped_column(String(64), default="", index=True)
    content_size: Mapped[int] = mapped_column(Integer, default=0)
    blob_uri: Mapped[str | None] = mapped_column(String(512), nullable=True)
    redaction_state: Mapped[str] = mapped_column(String(32), default="raw", index=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        PortableJSON, default=dict, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    trace: Mapped[AuditTraceORM] = relationship(back_populates="artifacts")


class AuditAgentDelegationORM(Base):
    __tablename__ = "audit_agent_delegations"
    __table_args__ = (
        UniqueConstraint(
            "trace_id",
            "parent_span_id",
            "child_span_id",
            name="uq_audit_agent_delegations_edge",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    trace_id: Mapped[str] = mapped_column(
        ForeignKey("audit_traces.trace_id", ondelete="CASCADE"),
        index=True,
    )
    parent_span_id: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    child_span_id: Mapped[str] = mapped_column(String(16), index=True)
    parent_agent_name: Mapped[str] = mapped_column(String(256), default="")
    child_agent_name: Mapped[str] = mapped_column(String(256), default="", index=True)
    tool_name: Mapped[str] = mapped_column(String(256), default="", index=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    attributes_json: Mapped[dict[str, Any]] = mapped_column(
        PortableJSON, default=dict, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class PromptFamilyORM(Base):
    __tablename__ = "prompt_families"
    __table_args__ = (
        UniqueConstraint("form_id", "task", "prompt_kind", name="uq_prompt_family_scope"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    form_id: Mapped[str] = mapped_column(String(128), index=True)
    task: Mapped[str] = mapped_column(String(64), default="audit_review", index=True)
    prompt_kind: Mapped[str] = mapped_column(String(64), default="instructions", index=True)
    name: Mapped[str] = mapped_column(String(160), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    external_registry_uri: Mapped[str | None] = mapped_column(String(512), nullable=True)
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(PortableJSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
    )

    versions: Mapped[list["PromptVersionORM"]] = relationship(
        back_populates="family",
        cascade="all, delete-orphan",
    )
    aliases: Mapped[list["PromptAliasORM"]] = relationship(
        back_populates="family",
        cascade="all, delete-orphan",
    )
    activations: Mapped[list["PromptActivationORM"]] = relationship(
        back_populates="family",
        cascade="all, delete-orphan",
    )


class PromptVersionORM(Base):
    __tablename__ = "prompt_versions"
    __table_args__ = (
        UniqueConstraint("family_id", "version_number", name="uq_prompt_version_number"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    family_id: Mapped[str] = mapped_column(ForeignKey("prompt_families.id"), index=True)
    version_number: Mapped[int] = mapped_column(Integer, index=True)
    text: Mapped[str] = mapped_column(Text)
    text_hash: Mapped[str] = mapped_column(String(64), index=True)
    components_json: Mapped[dict[str, Any] | None] = mapped_column(PortableJSON, nullable=True)
    source_kind: Mapped[str] = mapped_column(String(32), default="manual_edit", index=True)
    source_run_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    source_candidate_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_metadata_json: Mapped[dict[str, Any] | None] = mapped_column(
        PortableJSON,
        nullable=True,
    )
    commit_message: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[str] = mapped_column(String(120), default="system")
    metrics_json: Mapped[dict[str, Any] | None] = mapped_column(PortableJSON, nullable=True)
    applicable_form_versions_json: Mapped[list[str]] = mapped_column(
        PortableJSON,
        default=list,
        nullable=False,
    )
    form_schema_fingerprint: Mapped[str] = mapped_column(String(64), default="", index=True)
    external_prompt_uri: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    family: Mapped[PromptFamilyORM] = relationship(back_populates="versions")
    aliases: Mapped[list["PromptAliasORM"]] = relationship(back_populates="version")
    activations: Mapped[list["PromptActivationORM"]] = relationship(back_populates="version")


class PromptAliasORM(Base):
    __tablename__ = "prompt_aliases"
    __table_args__ = (UniqueConstraint("family_id", "alias", name="uq_prompt_alias_name"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    family_id: Mapped[str] = mapped_column(ForeignKey("prompt_families.id"), index=True)
    alias: Mapped[str] = mapped_column(String(64), index=True)
    version_id: Mapped[str] = mapped_column(ForeignKey("prompt_versions.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
    )

    family: Mapped[PromptFamilyORM] = relationship(back_populates="aliases")
    version: Mapped[PromptVersionORM] = relationship(back_populates="aliases")


class PromptActivationORM(Base):
    __tablename__ = "prompt_activations"
    __table_args__ = (
        UniqueConstraint("family_id", "scope_key", name="uq_prompt_activation_scope"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    family_id: Mapped[str] = mapped_column(ForeignKey("prompt_families.id"), index=True)
    version_id: Mapped[str] = mapped_column(ForeignKey("prompt_versions.id"), index=True)
    scope_key: Mapped[str] = mapped_column(String(96), index=True)
    scope: Mapped[str] = mapped_column(String(32), default="form_version", index=True)
    form_version: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    activated_by: Mapped[str] = mapped_column(String(120), default="user")
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        onupdate=utc_now,
    )

    family: Mapped[PromptFamilyORM] = relationship(back_populates="activations")
    version: Mapped[PromptVersionORM] = relationship(back_populates="activations")
