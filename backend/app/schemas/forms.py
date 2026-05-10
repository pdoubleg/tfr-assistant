from datetime import UTC, datetime

from pydantic import BaseModel, Field

from app.models.audit import AuditFormResult


class AuditFormDefinition(BaseModel):
    id: str
    version: str
    title: str
    description: str | None = None
    audit_scope: str | None = None
    tool_instructions: str | None = None
    canonical: AuditFormResult
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @property
    def catalog_key(self) -> str:
        return f"{self.id}@{self.version}"


class AuditFormRegistration(BaseModel):
    id: str
    version: str
    title: str
    description: str | None = None
    audit_scope: str | None = None
    tool_instructions: str | None = None
    canonical: AuditFormResult


class AuditFormSummary(BaseModel):
    id: str
    version: str
    title: str
    description: str | None = None
    audit_scope: str | None = None
    tool_instructions: str | None = None
    question_count: int
    sub_question_count: int = 0
    review_count: int = 0
    completed_count: int = 0
    failed_count: int = 0
    last_reviewed_at: datetime | None = None
    created_at: datetime | None = None
