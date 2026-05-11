from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON as SqlJSON
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utc_now() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class AuditBatchORM(Base):
    __tablename__ = "audit_batches"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    template_id: Mapped[str | None] = mapped_column(
        ForeignKey("audit_batch_templates.id"),
        nullable=True,
        index=True,
    )
    status: Mapped[str] = mapped_column(String(24), default="queued", index=True)
    source: Mapped[str] = mapped_column(String(32), default="batch")
    total_count: Mapped[int] = mapped_column(Integer, default=0)
    completed_count: Mapped[int] = mapped_column(Integer, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, default=0)
    input_json: Mapped[dict[str, Any] | None] = mapped_column(SqlJSON, nullable=True)
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
    synthetic: Mapped[bool] = mapped_column(default=False)
    synthetic_count: Mapped[int] = mapped_column(Integer, default=0)
    input_mode: Mapped[str] = mapped_column(String(24), default="manual")
    excel_column_map: Mapped[dict[str, Any] | None] = mapped_column(SqlJSON, nullable=True)
    items_json: Mapped[list[dict[str, Any]]] = mapped_column(SqlJSON, default=list)
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
        ForeignKey("audit_batches.id"),
        nullable=True,
        index=True,
    )
    form_id: Mapped[str] = mapped_column(String(128), index=True)
    form_version: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(24), default="queued", index=True)
    source: Mapped[str] = mapped_column(String(32), default="api", index=True)
    input_json: Mapped[dict[str, Any] | None] = mapped_column(SqlJSON, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    original_result_version_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    current_user_result_version_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
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
    review_id: Mapped[str] = mapped_column(ForeignKey("audit_reviews.id"), index=True)
    kind: Mapped[str] = mapped_column(String(16), index=True)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    payload_json: Mapped[dict[str, Any]] = mapped_column(SqlJSON)
    payload_hash: Mapped[str] = mapped_column(String(64), index=True)
    created_by: Mapped[str] = mapped_column(String(64), default="agent")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    review: Mapped[AuditReviewORM] = relationship(back_populates="versions")


class AuditQuestionAnswerORM(Base):
    __tablename__ = "audit_question_answers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    result_version_id: Mapped[str] = mapped_column(
        ForeignKey("audit_result_versions.id"),
        index=True,
    )
    review_id: Mapped[str] = mapped_column(ForeignKey("audit_reviews.id"), index=True)
    kind: Mapped[str] = mapped_column(String(16), index=True)
    question_id: Mapped[str] = mapped_column(String(64), index=True)
    question_text: Mapped[str] = mapped_column(Text)
    answer: Mapped[str] = mapped_column(String(8), index=True)
    position: Mapped[int] = mapped_column(Integer)


class AuditSubQuestionAnswerORM(Base):
    __tablename__ = "audit_subquestion_answers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    result_version_id: Mapped[str] = mapped_column(
        ForeignKey("audit_result_versions.id"),
        index=True,
    )
    review_id: Mapped[str] = mapped_column(ForeignKey("audit_reviews.id"), index=True)
    kind: Mapped[str] = mapped_column(String(16), index=True)
    question_id: Mapped[str] = mapped_column(String(64), index=True)
    subquestion_id: Mapped[str] = mapped_column(String(64), index=True)
    subquestion_text: Mapped[str] = mapped_column(Text)
    answer: Mapped[bool] = mapped_column(default=False)
    reasoning: Mapped[str] = mapped_column(Text, default="")
    citations: Mapped[str] = mapped_column(Text, default="")
    position: Mapped[int] = mapped_column(Integer)


class FeedbackORM(Base):
    __tablename__ = "review_feedback"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    review_id: Mapped[str] = mapped_column(ForeignKey("audit_reviews.id"), index=True)
    rating: Mapped[int] = mapped_column(Integer)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class EvaluationORM(Base):
    __tablename__ = "review_evaluations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    review_id: Mapped[str] = mapped_column(ForeignKey("audit_reviews.id"), index=True)
    evaluator: Mapped[str] = mapped_column(String(64), default="user")
    score: Mapped[float | None] = mapped_column(nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload_json: Mapped[dict[str, Any] | None] = mapped_column(SqlJSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class EvalDatasetORM(Base):
    __tablename__ = "eval_datasets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    form_id: Mapped[str] = mapped_column(String(128), index=True)
    form_version: Mapped[str] = mapped_column(String(64), index=True)
    source_kind: Mapped[str] = mapped_column(String(32), default="manual")
    source_metadata_json: Mapped[dict[str, Any] | None] = mapped_column(SqlJSON, nullable=True)
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
    input_json: Mapped[dict[str, Any] | None] = mapped_column(SqlJSON, nullable=True)
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
    payload_json: Mapped[dict[str, Any]] = mapped_column(SqlJSON)
    reviewer: Mapped[str | None] = mapped_column(String(120), nullable=True)
    source_metadata_json: Mapped[dict[str, Any] | None] = mapped_column(SqlJSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    case: Mapped[EvalCaseORM] = relationship(back_populates="ground_truths")
    comparisons: Mapped[list["EvalComparisonORM"]] = relationship(back_populates="ground_truth")


class EvalRunORM(Base):
    __tablename__ = "eval_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    dataset_id: Mapped[str] = mapped_column(ForeignKey("eval_datasets.id"), index=True)
    lineage_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    source_run_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    config_version: Mapped[int] = mapped_column(Integer, default=1)
    name: Mapped[str] = mapped_column(String(120), index=True)
    status: Mapped[str] = mapped_column(String(24), default="queued", index=True)
    model_name: Mapped[str] = mapped_column(String(128), default="")
    reference_policy: Mapped[str] = mapped_column(String(32), default="prefer_r2")
    concurrency: Mapped[int] = mapped_column(Integer, default=1)
    retry_limit: Mapped[int] = mapped_column(Integer, default=0)
    enable_mlflow: Mapped[bool] = mapped_column(Boolean, default=False)
    mlflow_run_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    total_count: Mapped[int] = mapped_column(Integer, default=0)
    completed_count: Mapped[int] = mapped_column(Integer, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, default=0)
    input_json: Mapped[dict[str, Any] | None] = mapped_column(SqlJSON, nullable=True)
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
        ForeignKey("audit_reviews.id"),
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
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    metrics_json: Mapped[dict[str, Any]] = mapped_column(SqlJSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    run_item: Mapped[EvalRunItemORM] = relationship(back_populates="comparisons")
    ground_truth: Mapped[EvalGroundTruthORM] = relationship(back_populates="comparisons")
