from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field


class FeedbackCreate(BaseModel):
    review_id: str
    rating: int = Field(..., ge=-1, le=1, description="-1 thumbs down, 0 neutral, 1 thumbs up")
    comment: str | None = None


class EvaluationSummary(BaseModel):
    review_count: int
    user_feedback_count: int
    edit_rate: float
    llm_judge_score: float | None = None


class EvaluationCreate(BaseModel):
    review_id: str
    evaluator: str = "user"
    score: float | None = None
    notes: str | None = None
    payload: dict[str, Any] | None = None


class EvaluationRecord(EvaluationCreate):
    id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
