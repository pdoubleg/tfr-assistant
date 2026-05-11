from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.schemas.evaluations import (
    EvalDatasetCreate,
    EvalDatasetDetail,
    EvalDatasetRecord,
    EvalRunCreate,
    EvalRunItemRecord,
    EvalRunRecord,
    EvaluationCreate,
    EvaluationRecord,
    EvaluationSummary,
    FeedbackCreate,
)
from app.services.evaluation_service import EvaluationRepository, run_evaluation_job
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


@router.get("/datasets", response_model=list[EvalDatasetRecord])
async def list_eval_datasets(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[EvalDatasetRecord]:
    return await EvaluationRepository(session).list_datasets()


@router.post("/datasets", response_model=EvalDatasetDetail, status_code=201)
async def create_eval_dataset(
    request: EvalDatasetCreate,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> EvalDatasetDetail:
    try:
        return await EvaluationRepository(session).create_dataset(request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/datasets/smoke-test", response_model=EvalDatasetDetail, status_code=201)
async def create_smoke_eval_dataset(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> EvalDatasetDetail:
    return await EvaluationRepository(session).create_smoke_dataset()


@router.get("/datasets/{dataset_id}", response_model=EvalDatasetDetail)
async def get_eval_dataset(
    dataset_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> EvalDatasetDetail:
    try:
        return await EvaluationRepository(session).get_dataset(dataset_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/runs", response_model=list[EvalRunRecord])
async def list_eval_runs(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[EvalRunRecord]:
    return await EvaluationRepository(session).list_runs()


@router.post("/runs", response_model=EvalRunRecord, status_code=201)
async def create_eval_run(
    request: EvalRunCreate,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> EvalRunRecord:
    try:
        run = await EvaluationRepository(session).create_run(request)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return run


@router.get("/runs/{run_id}", response_model=EvalRunRecord)
async def get_eval_run(
    run_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> EvalRunRecord:
    try:
        return await EvaluationRepository(session).get_run(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/runs/{run_id}/items", response_model=list[EvalRunItemRecord])
async def list_eval_run_items(
    run_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[EvalRunItemRecord]:
    try:
        return await EvaluationRepository(session).list_run_items(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/runs/{run_id}/pause", response_model=EvalRunRecord)
async def pause_eval_run(
    run_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> EvalRunRecord:
    try:
        return await EvaluationRepository(session).pause_run(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/runs/{run_id}/resume", response_model=EvalRunRecord)
async def resume_eval_run(
    run_id: str,
    background_tasks: BackgroundTasks,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> EvalRunRecord:
    try:
        run = await EvaluationRepository(session).resume_run(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    background_tasks.add_task(run_evaluation_job, run.id)
    return run


@router.post("/runs/{run_id}/cancel", response_model=EvalRunRecord)
async def cancel_eval_run(
    run_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> EvalRunRecord:
    try:
        return await EvaluationRepository(session).cancel_run(run_id)
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
