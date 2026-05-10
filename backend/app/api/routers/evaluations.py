from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.schemas.evaluations import (
    EvaluationCreate,
    EvaluationRecord,
    EvaluationSummary,
    FeedbackCreate,
)
from app.services.review_repository import ReviewRepository

router = APIRouter()


@router.get("/summary", response_model=EvaluationSummary)
async def get_evaluation_summary(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> EvaluationSummary:
    repository = ReviewRepository(session)
    review_count = await repository.review_count()
    edited_count = await repository.edited_review_count()
    edit_rate = edited_count / review_count if review_count else 0
    return EvaluationSummary(
        review_count=review_count,
        user_feedback_count=await repository.feedback_count(),
        edit_rate=edit_rate,
        llm_judge_score=None,
    )


@router.post("/feedback", response_model=FeedbackCreate, status_code=201)
async def add_feedback(
    feedback: FeedbackCreate,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> FeedbackCreate:
    try:
        return await ReviewRepository(session).add_feedback(feedback)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("", response_model=list[EvaluationRecord])
async def list_evaluations(
    session: Annotated[AsyncSession, Depends(get_session)],
    review_id: Annotated[str | None, Query()] = None,
) -> list[EvaluationRecord]:
    return await ReviewRepository(session).list_evaluations(review_id=review_id)


@router.post("", response_model=EvaluationRecord, status_code=201)
async def add_evaluation(
    evaluation: EvaluationCreate,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> EvaluationRecord:
    try:
        return await ReviewRepository(session).add_evaluation(evaluation)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
