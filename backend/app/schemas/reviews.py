from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.models.audit import AuditResult, FormKind
from app.schemas.prompts import PromptReference, ResolvedPrompt

ReviewStatus = Literal["queued", "running", "completed", "failed"]
ReviewSource = Literal[
    "api",
    "chat_tool",
    "batch",
    "batch_manual",
    "batch_upload",
    "synthetic",
    "completed_intake",
    "manual_entry",
    "eval",
]
BatchInputMode = Literal[
    "manual",
    "upload",
    "synthetic",
    "completed_intake",
    "manual_entry",
]
BatchStatus = Literal["queued", "running", "paused", "completed", "failed", "canceled"]
BatchReviewSource = Literal[
    "batch",
    "batch_manual",
    "batch_upload",
    "synthetic",
    "completed_intake",
    "manual_entry",
]
BATCH_REVIEW_SOURCES: tuple[BatchReviewSource, ...] = (
    "batch",
    "batch_manual",
    "batch_upload",
    "synthetic",
    "completed_intake",
    "manual_entry",
)


class ReviewCreate(BaseModel):
    source_file_ids: list[str] = Field(default_factory=list)
    form_id: str
    form_version: str
    notes: str | None = None


class ReviewGenerateRequest(BaseModel):
    prompt: str = ""
    claim_number: str = ""
    effective_date: str = ""
    instructions: str = ""
    form_id: str = "tfr_default"
    form_version: str = "v0.1"
    prompt_ref: PromptReference | None = None
    resolved_prompt: ResolvedPrompt | None = None
    source_file_ids: list[str] = Field(default_factory=list)
    synthetic: bool = False
    input_mode: BatchInputMode = "manual"
    generation_prompt: str = ""
    form_metadata: dict[str, str] = Field(default_factory=dict)
    manual_result: AuditResult | None = None
    eval_run_id: str = ""
    eval_run_name: str = ""
    eval_dataset_id: str = ""
    eval_result_role: str = ""
    eval_config_version: int | None = None


class ReviewRecord(BaseModel):
    id: str
    form_id: str
    form_version: str
    form_kind: FormKind = "standard"
    status: ReviewStatus = "completed"
    source: ReviewSource = "api"
    batch_id: str | None = None
    input_json: dict[str, Any] | None = None
    original: AuditResult | None = None
    user_version: AuditResult | None = None
    error_message: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ReviewUpdate(BaseModel):
    user_version: AuditResult
    comment: str | None = None


class BatchReviewInput(BaseModel):
    claim_number: str = ""
    effective_date: str = ""
    instructions: str = ""
    prompt: str = ""
    generation_prompt: str = ""
    source_file_ids: list[str] = Field(default_factory=list)
    form_id: str | None = None
    form_version: str | None = None
    synthetic: bool | None = None
    manual_result: AuditResult | None = None


class BatchCreateRequest(BaseModel):
    name: str = ""
    description: str = ""
    form_id: str = "tfr_default"
    form_version: str = "v0.1"
    synthetic: bool = False
    synthetic_count: int = Field(default=0, ge=0)
    input_mode: BatchInputMode = "manual"
    generation_prompt: str = ""
    prompt_ref: PromptReference | None = None
    excel_column_map: dict[str, str] = Field(default_factory=dict)
    items: list[BatchReviewInput] = Field(default_factory=list)


class BatchRecord(BaseModel):
    id: str
    template_id: str | None = None
    name: str = ""
    description: str = ""
    status: BatchStatus = "queued"
    source: str = "batch"
    total_count: int = 0
    completed_count: int = 0
    failed_count: int = 0
    running_count: int = 0
    queued_count: int = 0
    progress_percent: float = 0
    input_json: dict[str, Any] | None = None
    error_message: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_seconds: float | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class BatchFormVolume(BaseModel):
    form_id: str
    form_version: str
    form_kind: FormKind = "standard"
    total_count: int = 0
    completed_count: int = 0
    failed_count: int = 0


class BatchSummary(BaseModel):
    active_batches: int = 0
    queued_batches: int = 0
    paused_batches: int = 0
    failed_batches: int = 0
    completed_batches: int = 0
    total_reviews: int = 0
    completed_reviews: int = 0
    failed_reviews: int = 0
    running_reviews: int = 0
    queued_reviews: int = 0
    completed_reviews_today: int = 0
    average_duration_seconds: float | None = None
    form_volume: list[BatchFormVolume] = Field(default_factory=list)


class BatchTemplateCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    description: str = ""
    form_id: str = "tfr_default"
    form_version: str = "v0.1"
    synthetic: bool = False
    synthetic_count: int = Field(default=0, ge=0)
    input_mode: BatchInputMode = "manual"
    generation_prompt: str = ""
    prompt_ref: PromptReference | None = None
    excel_column_map: dict[str, str] = Field(default_factory=dict)
    items: list[BatchReviewInput] = Field(default_factory=list)


class BatchTemplateUpdate(BaseModel):
    description: str = ""
    form_id: str = "tfr_default"
    form_version: str = "v0.1"
    synthetic: bool = False
    synthetic_count: int = Field(default=0, ge=0)
    input_mode: BatchInputMode = "manual"
    generation_prompt: str = ""
    prompt_ref: PromptReference | None = None
    excel_column_map: dict[str, str] = Field(default_factory=dict)
    items: list[BatchReviewInput] = Field(default_factory=list)


class BatchTemplateRecord(BaseModel):
    id: str
    name: str
    description: str = ""
    form_id: str
    form_version: str
    synthetic: bool = False
    synthetic_count: int = 0
    input_mode: BatchInputMode = "manual"
    generation_prompt: str = ""
    prompt_ref: PromptReference | None = None
    excel_column_map: dict[str, str] = Field(default_factory=dict)
    items: list[BatchReviewInput] = Field(default_factory=list)
    item_count: int = 0
    latest_run: BatchRecord | None = None
    run_count: int = 0
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class IntakeDocumentRecord(BaseModel):
    id: str
    filename: str
    file_type: str
    size_bytes: int
    modified_at: datetime
    preview: str = ""
