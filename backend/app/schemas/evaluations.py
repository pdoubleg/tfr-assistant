from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.models.audit import AuditResult, FormKind
from app.schemas.prompts import PromptReference

EvalReferenceKind = Literal["R1", "R2"]
EvalReferencePolicy = Literal["prefer_r2", "r1", "r2", "all"]
EvalRunStatus = Literal["queued", "running", "paused", "completed", "failed", "canceled"]
EvalRunItemStatus = Literal["queued", "running", "completed", "failed", "skipped"]


class FeedbackCreate(BaseModel):
    review_id: str
    score: int = Field(..., ge=0, le=5, description="0-5 star rating")
    comment: str | None = None


class FeedbackRecord(FeedbackCreate):
    id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class EvaluationSummary(BaseModel):
    review_count: int
    user_feedback_count: int
    edit_rate: float
    llm_judge_score: float | None = None


class EvaluationCreate(BaseModel):
    review_id: str
    evaluator: str = "user"
    score: float | None = None
    notes: str | None = None
    payload: dict[str, Any] | None = None


class EvaluationRecord(EvaluationCreate):
    id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class EvalGroundTruthCreate(BaseModel):
    reference_kind: EvalReferenceKind
    result: AuditResult
    reviewer: str | None = None
    source_metadata: dict[str, Any] | None = None


class EvalCaseCreate(BaseModel):
    claim_number: str = Field(..., min_length=1)
    effective_date: str | None = None
    instructions: str = ""
    input: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] | None = None
    ground_truths: list[EvalGroundTruthCreate] = Field(default_factory=list)


class EvalDatasetCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    description: str = ""
    form_id: str = "tfr_default"
    form_version: str = "v0.1"
    form_kind: FormKind = "standard"
    source_kind: str = "manual"
    source_metadata: dict[str, Any] | None = None
    cases: list[EvalCaseCreate] = Field(default_factory=list)


class EvalGroundTruthRecord(BaseModel):
    id: str
    case_id: str
    reference_kind: EvalReferenceKind
    result: AuditResult
    reviewer: str | None = None
    source_metadata: dict[str, Any] | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class EvalCaseRecord(BaseModel):
    id: str
    dataset_id: str
    claim_number: str
    effective_date: str | None = None
    instructions: str = ""
    input: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] | None = None
    ground_truths: list[EvalGroundTruthRecord] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class EvalDatasetRecord(BaseModel):
    id: str
    name: str
    description: str = ""
    form_id: str
    form_version: str
    form_kind: FormKind = "standard"
    source_kind: str = "manual"
    source_metadata: dict[str, Any] | None = None
    dataset_hash: str
    case_count: int = 0
    r1_count: int = 0
    r2_count: int = 0
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class EvalDatasetDetail(EvalDatasetRecord):
    cases: list[EvalCaseRecord] = Field(default_factory=list)


class EvalRunCreate(BaseModel):
    dataset_id: str
    name: str = Field(..., min_length=1, max_length=120)
    model_name: str = ""
    reference_policy: EvalReferencePolicy = "prefer_r2"
    concurrency: int = Field(default=1, ge=1, le=10)
    retry_limit: int = Field(default=0, ge=0, le=3)
    enable_mlflow: bool = False
    prompt_ref: PromptReference | None = None
    base_run_id: str | None = None


class EvalAgreementItemRecord(BaseModel):
    id: str
    run_id: str
    run_item_id: str
    case_id: str
    ground_truth_id: str
    comparison_id: str
    reference_kind: EvalReferenceKind
    form_kind: FormKind = "standard"
    level: Literal["overall", "question", "subquestion", "financial_question"]
    question_id: str | None = None
    subquestion_id: str | None = None
    question_text: str | None = None
    subquestion_text: str | None = None
    generated_answer: str | None = None
    reference_answer: str | None = None
    matched: bool
    agreement: float
    generated_comment: str | None = None
    reference_comment: str | None = None
    generated_citations: str | None = None
    reference_citations: str | None = None
    generated_overwrite_dollars: float | None = None
    reference_overwrite_dollars: float | None = None
    generated_underwrite_dollars: float | None = None
    reference_underwrite_dollars: float | None = None
    overwrite_dollar_error: float | None = None
    underwrite_dollar_error: float | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class EvalComparisonRecord(BaseModel):
    id: str
    run_id: str
    run_item_id: str
    case_id: str
    ground_truth_id: str
    reference_kind: EvalReferenceKind
    form_kind: FormKind = "standard"
    score: float | None = None
    metrics: dict[str, Any] = Field(default_factory=dict)
    agreement_items: list[EvalAgreementItemRecord] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class EvalRunItemRecord(BaseModel):
    id: str
    run_id: str
    case_id: str
    claim_number: str
    effective_date: str | None = None
    status: EvalRunItemStatus = "queued"
    attempt_count: int = 0
    generated_review_id: str | None = None
    generated_result: AuditResult | None = None
    ground_truths: list[EvalGroundTruthRecord] = Field(default_factory=list)
    error_message: str | None = None
    comparisons: list[EvalComparisonRecord] = Field(default_factory=list)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class EvalRunRecord(BaseModel):
    id: str
    dataset_id: str
    dataset_name: str = ""
    form_kind: FormKind = "standard"
    lineage_id: str | None = None
    source_run_id: str | None = None
    config_version: int = 1
    name: str
    status: EvalRunStatus = "queued"
    model_name: str = ""
    reference_policy: EvalReferencePolicy = "prefer_r2"
    concurrency: int = 1
    retry_limit: int = 0
    enable_mlflow: bool = False
    prompt_ref: PromptReference | None = None
    mlflow_run_id: str | None = None
    total_count: int = 0
    completed_count: int = 0
    failed_count: int = 0
    running_count: int = 0
    queued_count: int = 0
    progress_percent: float = 0
    primary_score: float | None = None
    metrics: dict[str, Any] = Field(default_factory=dict)
    input: dict[str, Any] = Field(default_factory=dict)
    error_message: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_seconds: float | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
