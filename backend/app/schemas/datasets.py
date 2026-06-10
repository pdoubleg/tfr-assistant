from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from app.models.audit import AuditResult, FormKind

DatasetPopulationStatus = Literal["draft", "published"]
DatasetFeedbackFilter = Literal["all", "with_feedback", "without_feedback", "low_score"]
DatasetSampleMode = Literal[
    "all",
    "random",
    "outcome",
    "stratified_outcome_issues",
    "cluster_balanced",
    "diversity",
]


class DatasetReference(BaseModel):
    reference_kind: Literal["R1", "R2"]
    result: AuditResult
    reviewer: str | None = None
    source_metadata: dict[str, Any] | None = None


class CanonicalDatasetCandidate(BaseModel):
    source_key: str
    source_record_id: str
    source_kind: str = "external_named_query"
    source_label: str = ""
    claim_number: str = Field(..., min_length=1)
    effective_date: str | None = None
    instructions: str = ""
    input: dict[str, Any] = Field(default_factory=dict)
    references: list[DatasetReference] = Field(default_factory=list)
    metadata: dict[str, Any] | None = None
    tags: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_references(self) -> "CanonicalDatasetCandidate":
        if not self.references:
            raise ValueError("Candidate must include at least one reference result.")
        return self


class DatasetPopulationCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    description: str = ""
    form_id: str
    form_version: str


class DatasetPopulationUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = None


class DatasetPopulationRecord(BaseModel):
    id: str
    name: str
    description: str = ""
    form_id: str
    form_version: str
    form_kind: FormKind = "standard"
    status: DatasetPopulationStatus = "draft"
    source_config: dict[str, Any] | None = None
    cluster_config: dict[str, Any] | None = None
    sample_config: dict[str, Any] | None = None
    published_dataset_id: str | None = None
    candidate_count: int = 0
    included_count: int = 0
    clustered_count: int = 0
    r1_count: int = 0
    r2_count: int = 0
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class DatasetCandidateRecord(BaseModel):
    id: str
    population_id: str
    source_kind: str
    source_key: str
    source_label: str = ""
    source_record_id: str
    dedupe_key: str
    claim_number: str
    effective_date: str | None = None
    instructions: str = ""
    input: dict[str, Any] = Field(default_factory=dict)
    references: list[DatasetReference] = Field(default_factory=list)
    metadata: dict[str, Any] | None = None
    tags: list[str] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)
    included: bool = True
    cluster_id: int | None = None
    cluster_distance: float | None = None
    cluster_score: float | None = None
    cluster_metadata: dict[str, Any] | None = None
    sample_reason: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class DatasetPopulationDetail(DatasetPopulationRecord):
    candidates: list[DatasetCandidateRecord] = Field(default_factory=list)


class DatasetCandidateUpdate(BaseModel):
    included: bool | None = None
    tags: list[str] | None = None
    sample_reason: str | None = None


class DatasetCandidateReferenceUpdate(BaseModel):
    result: AuditResult
    reviewer: str | None = None
    source_metadata: dict[str, Any] | None = None


class DatasetAddCandidatesResponse(BaseModel):
    population: DatasetPopulationRecord
    added_count: int
    skipped_count: int
    candidate_ids: list[str] = Field(default_factory=list)


class DatasetAppDbBrowseRequest(BaseModel):
    search: str = ""
    source: str = "all"
    outcome: str = "all"
    result_version: Literal["current", "original"] = "current"
    include_feedback: bool = False
    feedback_filter: DatasetFeedbackFilter = "all"
    limit: int = Field(default=100, ge=1, le=1000)


class DatasetAppDbAddRequest(DatasetAppDbBrowseRequest):
    review_ids: list[str] = Field(default_factory=list)
    add_all_filtered: bool = False


class DatasetSourceRowRecord(BaseModel):
    source_record_id: str
    review_id: str = ""
    source_id: str = ""
    source_kind: str = ""
    source_label: str = ""
    result_version: Literal["current", "original"] = "current"
    source: str = ""
    claim_number: str = ""
    effective_date: str | None = None
    title: str = ""
    outcome: str = ""
    issue_count: int = 0
    driver_count: int = 0
    total_amount_reviewed_dollars: float | None = None
    total_overwrite_dollars: float = 0
    total_underwrite_dollars: float = 0
    feedback_count: int = 0
    feedback_average_score: float | None = None
    feedback_min_score: int | None = None
    feedback_latest_score: int | None = None
    feedback_latest_comment: str | None = None
    feedback_latest_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class DatasetClusterRequest(BaseModel):
    min_clusters: int = Field(default=2, ge=1, le=25)
    max_clusters: int = Field(default=6, ge=1, le=50)
    seed: int = 0
    semantic_weight: float = Field(default=0.75, ge=0, le=1)
    structured_weight: float = Field(default=0.25, ge=0, le=1)

    @model_validator(mode="after")
    def validate_range(self) -> "DatasetClusterRequest":
        if self.max_clusters < self.min_clusters:
            raise ValueError("max_clusters must be greater than or equal to min_clusters.")
        return self


class DatasetClusterResult(BaseModel):
    population: DatasetPopulationRecord
    feature_backend: str
    selected_k: int
    clustered_count: int
    silhouette_score: float | None = None
    cluster_counts: dict[str, int] = Field(default_factory=dict)


class DatasetSampleRequest(BaseModel):
    mode: DatasetSampleMode = "all"
    size: int | None = Field(default=None, ge=1, le=10000)
    seed: int = 0


class DatasetSampleResult(BaseModel):
    population: DatasetPopulationRecord
    selected_count: int
    mode: DatasetSampleMode
    sample_config: dict[str, Any] = Field(default_factory=dict)


class DatasetPublishRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    description: str = ""
    include_only: bool = True


class DatasetCloneRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = None


class PublishedDatasetRow(BaseModel):
    dataset_id: str
    dataset_name: str
    case_id: str
    ground_truth_id: str
    reference_kind: Literal["R1", "R2"]
    form_id: str
    form_version: str
    form_kind: FormKind = "standard"
    claim_number: str = ""
    effective_date: str | None = None
    source_kind: str = ""
    source_key: str = ""
    source_label: str = ""
    source_record_id: str = ""
    cluster_id: int | None = None
    sample_reason: str = ""
    metadata: dict[str, Any] | None = None
    result: AuditResult
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
