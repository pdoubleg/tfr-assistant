from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field, model_validator

from app.models.audit import AuditResult, FormKind


def _legacy_instructions(data: Any) -> Any:
    if not isinstance(data, dict) or data.get("instructions"):
        return data
    sections = []
    audit_scope = (data.get("audit_scope") or "").strip()
    tool_instructions = (data.get("tool_instructions") or "").strip()
    if audit_scope:
        sections.append(f"Audit Scope:\n{audit_scope}")
    if tool_instructions:
        sections.append(f"Tool Instructions:\n{tool_instructions}")
    if sections:
        data = dict(data)
        data["instructions"] = "\n\n".join(sections)
    return data


def _normalize_form_kind(data: Any) -> Any:
    data = _legacy_instructions(data)
    if not isinstance(data, dict):
        return data
    canonical = data.get("canonical")
    form_kind = data.get("form_kind") or "standard"
    if isinstance(canonical, dict):
        canonical_kind = canonical.get("form_kind") or form_kind
        canonical = {**canonical, "form_kind": canonical_kind}
        data = {**data, "canonical": canonical, "form_kind": canonical_kind}
    else:
        data = {**data, "form_kind": form_kind}
    return data


class AuditFormDefinition(BaseModel):
    id: str
    version: str
    title: str
    form_kind: FormKind = "standard"
    description: str | None = None
    instructions: str | None = None
    tools: list[str] | None = None
    knowledge_docs: list[str] | None = None
    canonical: AuditResult
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="before")
    @classmethod
    def migrate_legacy_prompt_fields(cls, data: Any) -> Any:
        return _normalize_form_kind(data)

    @model_validator(mode="after")
    def validate_form_kind(self) -> "AuditFormDefinition":
        if self.canonical.form_kind != self.form_kind:
            raise ValueError("form_kind must match canonical.form_kind.")
        return self

    @property
    def catalog_key(self) -> str:
        return f"{self.id}@{self.version}"


class AuditFormRegistration(BaseModel):
    id: str
    version: str
    title: str
    form_kind: FormKind = "standard"
    description: str | None = None
    instructions: str | None = None
    tools: list[str] | None = None
    knowledge_docs: list[str] | None = None
    canonical: AuditResult

    @model_validator(mode="before")
    @classmethod
    def migrate_legacy_prompt_fields(cls, data: Any) -> Any:
        return _normalize_form_kind(data)

    @model_validator(mode="after")
    def validate_form_kind(self) -> "AuditFormRegistration":
        if self.canonical.form_kind != self.form_kind:
            raise ValueError("form_kind must match canonical.form_kind.")
        return self


class AuditFormSummary(BaseModel):
    id: str
    version: str
    title: str
    form_kind: FormKind = "standard"
    description: str | None = None
    instructions: str | None = None
    tools: list[str] | None = None
    knowledge_docs: list[str] | None = None
    question_count: int
    sub_question_count: int = 0
    review_count: int = 0
    completed_count: int = 0
    failed_count: int = 0
    last_reviewed_at: datetime | None = None
    created_at: datetime | None = None
