"""Caller-controlled inputs and extraction envelopes, separate from LLM features."""

from datetime import date as Date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .models import BaselineClaimFeatures, ClaimLLMFeatures, SupplementMechanismFeatures

SCHEMA_VERSION = "1.0"
PROMPT_VERSION = "1.0"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Evidence(StrictModel):
    id: str = Field(min_length=1)
    source: str = Field(min_length=1)
    kind: Literal["note", "estimate", "photo_description", "document"]
    date: Date | None = None
    text: str = Field(min_length=1)


class ClaimBundle(StrictModel):
    claim_id: str = Field(min_length=1)
    hover: bool
    peril: str | None = None
    sub_peril: str | None = None
    dol: Date | None = None
    fnol_date: Date | None = None
    initial_estimate_cutoff: Date
    initial_estimate_amount: float | None = Field(default=None, ge=0)
    supplement_approved_amount: float | None = Field(default=None, ge=0)
    supplement_requested_amount: float | None = Field(default=None, ge=0)
    supplement_denied_amount: float | None = Field(default=None, ge=0)
    revised_estimate_amount: float | None = Field(default=None, ge=0)
    supplement_activity: Literal["yes", "no", "unknown"] = "unknown"
    sampling_weight: float = Field(default=1, gt=0)
    initial_evidence: list[Evidence]
    later_evidence: list[Evidence] = Field(default_factory=list)

    @model_validator(mode="after")
    def consistent_evidence(self):
        all_ids = [e.id for e in self.initial_evidence + self.later_evidence]
        if len(all_ids) != len(set(all_ids)):
            raise ValueError("Evidence IDs must be unique within a claim")
        if any(e.date and e.date > self.initial_estimate_cutoff for e in self.initial_evidence):
            raise ValueError("Initial evidence cannot be dated after the cutoff")
        if self.supplement_activity == "no" and any(
            (getattr(self, f) or 0) > 0
            for f in (
                "supplement_approved_amount",
                "supplement_requested_amount",
                "supplement_denied_amount",
            )
        ):
            raise ValueError("No supplement activity conflicts with positive supplement dollars")
        return self

    def metadata(self) -> dict:
        return self.model_dump(mode="json", exclude={"initial_evidence", "later_evidence"})


class EvidenceReference(StrictModel):
    field_path: str = Field(description="Feature path, e.g. damage.water_damage")
    evidence_ids: list[str] = Field(min_length=1)
    explanation: str = Field(min_length=1)


class BaselineOutput(StrictModel):
    features: BaselineClaimFeatures
    evidence: list[EvidenceReference] = Field(default_factory=list)


class SupplementOutput(StrictModel):
    features: SupplementMechanismFeatures
    evidence: list[EvidenceReference] = Field(default_factory=list)


class PassResult(StrictModel):
    status: Literal["success", "failed", "skipped"]
    features: BaselineClaimFeatures | SupplementMechanismFeatures | None = None
    evidence: list[EvidenceReference] = Field(default_factory=list)
    error: str | None = None
    usage: dict[str, int] = Field(default_factory=dict)
    cost: float = 0
    latency: float = 0

    @model_validator(mode="after")
    def complete_status(self):
        if self.status in {"success", "skipped"} and self.features is None:
            raise ValueError("Successful/skipped extraction requires a feature record")
        return self


class ExtractionResult(StrictModel):
    claim_id: str
    baseline: PassResult
    supplement: PassResult
    discrepancies: list[dict] = Field(default_factory=list)
    model_config_used: dict = Field(default_factory=dict)
    schema_version: str = SCHEMA_VERSION
    prompt_version: str = PROMPT_VERSION
    cache_key: str = ""

    @model_validator(mode="after")
    def correct_pass_types(self):
        if self.baseline.features is not None and not isinstance(
            self.baseline.features, BaselineClaimFeatures
        ):
            raise ValueError("Baseline pass requires baseline features")
        if self.supplement.features is not None and not isinstance(
            self.supplement.features, SupplementMechanismFeatures
        ):
            raise ValueError("Supplement pass requires supplement features")
        if self.baseline.status == "skipped":
            raise ValueError("Baseline extraction cannot be skipped")
        return self

    @property
    def status(self) -> str:
        return "failed" if "failed" in (self.baseline.status, self.supplement.status) else "success"

    @property
    def features(self) -> ClaimLLMFeatures | None:
        if self.baseline.features is None or self.supplement.features is None:
            return None
        return ClaimLLMFeatures(
            baseline=self.baseline.features,
            supplement_mechanism=self.supplement.features,
        )
