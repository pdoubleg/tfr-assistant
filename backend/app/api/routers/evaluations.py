from fastapi import APIRouter

from app.schemas.evaluations import EvaluationSummary, FeedbackCreate
from app.services.review_store import review_store

router = APIRouter()
_feedback: list[FeedbackCreate] = []


@router.get("/summary", response_model=EvaluationSummary)
def get_evaluation_summary() -> EvaluationSummary:
    reviews = review_store.list_reviews()
    edited_count = sum(
        review.original.model_dump() != review.user_version.model_dump() for review in reviews
    )
    edit_rate = edited_count / len(reviews) if reviews else 0
    return EvaluationSummary(
        review_count=len(reviews),
        user_feedback_count=len(_feedback),
        edit_rate=edit_rate,
        llm_judge_score=None,
    )


@router.post("/feedback", response_model=FeedbackCreate, status_code=201)
def add_feedback(feedback: FeedbackCreate) -> FeedbackCreate:
    _feedback.append(feedback)
    return feedback
