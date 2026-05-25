from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

PromptTask = Literal["audit_review"]
PromptKind = Literal["instructions"]
PromptSourceKind = Literal["form_default", "handcrafted", "manual_edit", "gepa_candidate"]
PromptRefType = Literal["form_default", "alias", "version", "manual"]


class PromptReference(BaseModel):
    ref_type: PromptRefType = "form_default"
    family_id: str | None = None
    alias: str | None = None
    version_id: str | None = None
    form_id: str | None = None
    task: PromptTask = "audit_review"
    prompt_kind: PromptKind = "instructions"
    manual_text: str = ""

    @model_validator(mode="after")
    def validate_reference(self) -> PromptReference:
        if self.ref_type == "alias" and not (self.family_id and self.alias):
            raise ValueError("Alias prompt references require family_id and alias.")
        if self.ref_type == "version" and not self.version_id:
            raise ValueError("Version prompt references require version_id.")
        if self.ref_type == "manual" and not self.manual_text.strip():
            raise ValueError("Manual prompt references require manual_text.")
        return self


class ResolvedPrompt(BaseModel):
    ref: PromptReference
    text: str
    text_hash: str
    family_id: str | None = None
    version_id: str | None = None
    version_number: int | None = None
    alias: str | None = None
    form_id: str | None = None
    source_kind: str = "form_default"
    external_prompt_uri: str | None = None
    resolved_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class PromptAliasRecord(BaseModel):
    id: str
    family_id: str
    alias: str
    version_id: str
    version_number: int | None = None
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class PromptVersionRecord(BaseModel):
    id: str
    family_id: str
    version_number: int
    text: str
    text_hash: str
    source_kind: PromptSourceKind
    source_run_id: str | None = None
    source_candidate_index: int | None = None
    source_metadata: dict[str, Any] = Field(default_factory=dict)
    commit_message: str = ""
    created_by: str = "system"
    metrics: dict[str, Any] = Field(default_factory=dict)
    applicable_form_versions: list[str] = Field(default_factory=list)
    form_schema_fingerprint: str = ""
    external_prompt_uri: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class PromptFamilyRecord(BaseModel):
    id: str
    form_id: str
    task: PromptTask = "audit_review"
    prompt_kind: PromptKind = "instructions"
    name: str
    description: str = ""
    external_registry_uri: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    aliases: list[PromptAliasRecord] = Field(default_factory=list)
    versions: list[PromptVersionRecord] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class PromptVersionCreate(BaseModel):
    family_id: str | None = None
    form_id: str
    form_version: str | None = None
    text: str = Field(..., min_length=1)
    source_kind: PromptSourceKind = "manual_edit"
    source_run_id: str | None = None
    source_candidate_index: int | None = None
    source_metadata: dict[str, Any] = Field(default_factory=dict)
    commit_message: str = ""
    created_by: str = "user"
    metrics: dict[str, Any] = Field(default_factory=dict)
    applicable_form_versions: list[str] = Field(default_factory=list)
    external_prompt_uri: str | None = None
    alias: str | None = None


class PromptAliasUpdate(BaseModel):
    family_id: str
    alias: str = Field(..., min_length=1, max_length=64)
    version_id: str


class OptimizationCandidatePromotion(BaseModel):
    run_id: str
    candidate_index: int
    alias: str | None = "champion"
    commit_message: str = ""
    created_by: str = "user"
