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
