from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from app.models.audit import FormKind
from app.schemas.prompts import PromptReference, ResolvedPrompt

OptimizationRunStatus = Literal["queued", "running", "completed", "failed", "canceled"]
OptimizationSplit = Literal["train", "val", "test"]
OptimizationSeedSource = Literal["form", "manual", "prompt_registry"]
OptimizationMetricMode = Literal["comparison", "comparison_with_judge"]
OptimizationScoreKey = Literal[
    "score",
    "question_agreement",
    "path_exact_rate",
    "subquestion_f1",
    "outcome_score",
    "financial_score",
    "total_overwrite_agreement",
    "total_underwrite_agreement",
    "overwrite_percent_agreement",
    "underwrite_percent_agreement",
    "question_financial_agreement",
    "absolute_dollar_error_score",
    "percent_error_score",
]
OptimizationReferencePolicy = Literal["prefer_r2", "r1", "r2", "all"]
OptimizationAutoBudget = Literal["light", "medium", "heavy"]
OptimizationCandidateSelectionStrategy = Literal[
    "pareto",
    "current_best",
    "epsilon_greedy",
    "top_k_pareto",
]
OptimizationFrontierType = Literal["instance", "objective", "hybrid", "cartesian"]
OptimizationBatchSampler = Literal["epoch_shuffled"]
OptimizationValEvaluationPolicy = Literal["full_eval"]


class OptimizationGepaParams(BaseModel):
    auto: OptimizationAutoBudget | None = None
    max_full_evals: int | None = Field(default=None, ge=1, le=100)
    max_metric_calls: int | None = Field(default=24, ge=1, le=5000)

    reflection_model: str | None = None
    reflection_minibatch_size: int | None = Field(default=3, ge=1, le=100)
    perfect_score: float = Field(default=1.0, ge=0.0)
    skip_perfect_score: bool = True

    candidate_selection_strategy: OptimizationCandidateSelectionStrategy = "pareto"
    frontier_type: OptimizationFrontierType = "instance"
    batch_sampler: OptimizationBatchSampler = "epoch_shuffled"
    module_selector: str = "all"

    use_merge: bool = False
    max_merge_invocations: int = Field(default=5, ge=0, le=100)
    merge_val_overlap_floor: int = Field(default=5, ge=0, le=100)

    cache_evaluation: bool = False
    track_best_outputs: bool = False
    display_progress_bar: bool = False
    raise_on_exception: bool = False
    val_evaluation_policy: OptimizationValEvaluationPolicy | None = None

    use_mlflow: bool = False
    mlflow_tracking_uri: str | None = None
    mlflow_experiment_name: str | None = None

    seed: int = 0

    @model_validator(mode="after")
    def validate_budget_group(self) -> OptimizationGepaParams:
        budget_count = sum(
            item is not None for item in (self.max_metric_calls, self.max_full_evals, self.auto)
        )
        if budget_count != 1:
            raise ValueError(
                "Exactly one GEPA budget option must be set: "
                "max_metric_calls, max_full_evals, or auto."
            )
        return self


class OptimizationTraceConfig(BaseModel):
    capture_traces: bool = True
    max_tool_return_chars: int = Field(default=2000, ge=100, le=20000)
    include_debug_traces: bool = True
    include_thinking: bool = True


class OptimizationCaseSplit(BaseModel):
    case_id: str
    split: OptimizationSplit


class OptimizationRunCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    form_id: str
    form_version: str
    seed_instruction_source: OptimizationSeedSource = "prompt_registry"
    manual_instructions: str = ""
    seed_prompt_ref: PromptReference | None = None
    resolved_seed_prompt: ResolvedPrompt | None = None
    metric_mode: OptimizationMetricMode = "comparison"
    score_key: OptimizationScoreKey = "score"
    reference_policy: OptimizationReferencePolicy = "prefer_r2"
    judge_model: str | None = None
    use_feedback_when_available: bool = False
    judge_score_weight: float = Field(default=0.0, ge=0.0, le=1.0)
    gepa_params: OptimizationGepaParams = Field(default_factory=OptimizationGepaParams)
    trace_config: OptimizationTraceConfig = Field(default_factory=OptimizationTraceConfig)
    case_splits: list[OptimizationCaseSplit] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_config(self) -> OptimizationRunCreate:
        if self.seed_instruction_source == "manual" and not self.manual_instructions.strip():
            raise ValueError("Manual instructions are required when seed source is manual.")
        split_counts = {split: 0 for split in ("train", "val", "test")}
        for item in self.case_splits:
            split_counts[item.split] += 1
        if split_counts["train"] < 1:
            raise ValueError("Optimization runs require at least one train case.")
        if split_counts["val"] < 1:
            raise ValueError("Optimization runs require at least one validation case.")
        return self


class OptimizationCaseRecord(BaseModel):
    case_id: str
    dataset_id: str
    dataset_name: str
    source_kind: str
    form_kind: FormKind = "standard"
    claim_number: str
    effective_date: str | None = None
    instructions: str = ""
    outcome: str
    issue_count: int
    driver_count: int
    reference_kinds: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class OptimizationCandidateRecord(BaseModel):
    id: str
    run_id: str
    candidate_index: int
    parent_indices: list[int | None] = Field(default_factory=list)
    status: str = "candidate"
    candidate: dict[str, str] = Field(default_factory=dict)
    score: float | None = None
    metrics: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class OptimizationEventRecord(BaseModel):
    id: str
    run_id: str
    sequence: int
    type: str
    message: str = ""
    iteration: int | None = None
    level: str = "info"
    data: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class OptimizationRunRecord(BaseModel):
    id: str
    name: str
    status: OptimizationRunStatus
    form_id: str
    form_version: str
    form_kind: FormKind = "standard"
    config: dict[str, Any] = Field(default_factory=dict)
    case_splits: list[OptimizationCaseSplit] = Field(default_factory=list)
    seed_candidate: dict[str, str] | None = None
    best_candidate: dict[str, str] | None = None
    metrics: dict[str, Any] = Field(default_factory=dict)
    artifacts: dict[str, Any] = Field(default_factory=dict)
    token_usage: dict[str, Any] = Field(default_factory=dict)
    total_count: int = 0
    train_count: int = 0
    val_count: int = 0
    test_count: int = 0
    best_score: float | None = None
    original_score: float | None = None
    total_metric_calls: int = 0
    error_message: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    candidates: list[OptimizationCandidateRecord] = Field(default_factory=list)
    events: list[OptimizationEventRecord] = Field(default_factory=list)
