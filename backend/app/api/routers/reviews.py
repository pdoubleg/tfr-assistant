from fastapi import APIRouter, HTTPException

from app.models.audit import AuditFormResult
from app.schemas.reviews import ReviewRecord, ReviewUpdate
from app.services.review_store import review_store

router = APIRouter()


@router.get("", response_model=list[ReviewRecord])
def list_reviews() -> list[ReviewRecord]:
    return review_store.list_reviews()


@router.get("/{review_id}", response_model=ReviewRecord)
def get_review(review_id: str) -> ReviewRecord:
    try:
        return review_store.get_review(review_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/agent-output", response_model=ReviewRecord, status_code=201)
def persist_agent_output(result: AuditFormResult) -> ReviewRecord:
    return review_store.create_from_agent_output(result)


@router.put("/{review_id}/user-version", response_model=ReviewRecord)
def update_user_version(review_id: str, update: ReviewUpdate) -> ReviewRecord:
    try:
        return review_store.update_user_version(review_id, update)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
