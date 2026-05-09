from datetime import UTC, datetime

from pydantic import BaseModel, Field

from app.models.audit import AuditFormResult


class AuditFormDefinition(BaseModel):
    id: str
    version: str
    title: str
    description: str | None = None
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
    canonical: AuditFormResult


class AuditFormSummary(BaseModel):
    id: str
    version: str
    title: str
    description: str | None = None
    question_count: int

