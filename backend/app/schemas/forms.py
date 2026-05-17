from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field, model_validator

from app.models.audit import AuditFormResult


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


class AuditFormDefinition(BaseModel):
    id: str
    version: str
    title: str
    description: str | None = None
    instructions: str | None = None
    tools: list[str] | None = None
    knowledge_docs: list[str] | None = None
    canonical: AuditFormResult
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="before")
    @classmethod
    def migrate_legacy_prompt_fields(cls, data: Any) -> Any:
        return _legacy_instructions(data)

    @property
    def catalog_key(self) -> str:
        return f"{self.id}@{self.version}"


class AuditFormRegistration(BaseModel):
    id: str
    version: str
    title: str
    description: str | None = None
    instructions: str | None = None
    tools: list[str] | None = None
    knowledge_docs: list[str] | None = None
    canonical: AuditFormResult

    @model_validator(mode="before")
    @classmethod
    def migrate_legacy_prompt_fields(cls, data: Any) -> Any:
        return _legacy_instructions(data)


class AuditFormSummary(BaseModel):
    id: str
    version: str
    title: str
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
