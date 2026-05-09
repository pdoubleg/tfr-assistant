from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.models.audit import AuditFormResult


class ReviewCreate(BaseModel):
    source_file_ids: list[str] = Field(default_factory=list)
    form_id: str
    form_version: str
    notes: str | None = None


class ReviewRecord(BaseModel):
    id: str
    form_id: str
    form_version: str
    status: Literal["queued", "running", "completed", "failed"] = "completed"
    original: AuditFormResult
    user_version: AuditFormResult
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ReviewUpdate(BaseModel):
    user_version: AuditFormResult
    comment: str | None = None

