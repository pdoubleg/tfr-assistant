from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.models.audit import AuditResult
from app.schemas.reviews import (
    ReviewFinalization,
    ReviewGenerateRequest,
    ReviewRecord,
    ReviewUpdate,
)
from app.services.audit_generation import AuditGenerationService
from app.services.review_repository import ReviewRepository

router = APIRouter()


@router.get("", response_model=list[ReviewRecord])
async def list_reviews(
    session: Annotated[AsyncSession, Depends(get_session)],
    batch_id: Annotated[str | None, Query()] = None,
) -> list[ReviewRecord]:
    return await ReviewRepository(session).list_reviews(batch_id=batch_id)


@router.get("/{review_id}", response_model=ReviewRecord)
async def get_review(
    review_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ReviewRecord:
    try:
        return await ReviewRepository(session).get_review(review_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/agent-output", response_model=ReviewRecord, status_code=201)
async def persist_agent_output(
    result: AuditResult,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ReviewRecord:
    return await ReviewRepository(session).create_from_agent_output(result)


@router.post("/generate", response_model=ReviewRecord, status_code=201)
async def generate_review(
    request: ReviewGenerateRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ReviewRecord:
    return await AuditGenerationService(session).generate_new_review(request, source="api")


@router.put("/{review_id}/user-version", response_model=ReviewRecord)
async def update_user_version(
    review_id: str,
    update: ReviewUpdate,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ReviewRecord:
    try:
        return await ReviewRepository(session).update_user_version(review_id, update)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put("/{review_id}/finalization", response_model=ReviewRecord)
async def finalize_review(
    review_id: str,
    update: ReviewFinalization,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ReviewRecord:
    try:
        return await ReviewRepository(session).finalize_review(review_id, update)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
