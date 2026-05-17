from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.db.session import get_session
from app.schemas.reviews import (
    BatchCreateRequest,
    BatchRecord,
    BatchSummary,
    BatchTemplateCreate,
    BatchTemplateRecord,
    BatchTemplateUpdate,
    ReviewRecord,
)
from app.services.audit_generation import BatchReviewGenerationService, run_batch_job
from app.services.catalog import FormCatalog
from app.services.review_repository import ReviewRepository

router = APIRouter()


def validate_registered_forms(
    request: BatchCreateRequest | BatchTemplateCreate | BatchTemplateUpdate,
    settings: Settings,
) -> None:
    catalog = FormCatalog(settings.form_catalog_dir)
    try:
        catalog.get_form(request.form_id, request.form_version)
    except KeyError as exc:
        raise HTTPException(
            status_code=400,
            detail=(
                "Registered form "
                f"{request.form_id}@{request.form_version} was not found in the form catalog."
            ),
        ) from exc

    for index, item in enumerate(request.items, start=1):
        form_id = item.form_id or request.form_id
        form_version = item.form_version or request.form_version
        try:
            catalog.get_form(form_id, form_version)
        except KeyError as exc:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Review row {index} references registered form "
                    f"{form_id}@{form_version}, but that canonical JSON was not found."
                ),
            ) from exc


@router.get("/templates", response_model=list[BatchTemplateRecord])
async def list_batch_templates(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[BatchTemplateRecord]:
    return await ReviewRepository(session).list_batch_templates()


@router.get("/summary", response_model=BatchSummary)
async def get_batch_summary(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> BatchSummary:
    return await ReviewRepository(session).batch_summary()


@router.get("", response_model=list[BatchRecord])
async def list_batches(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[BatchRecord]:
    return await ReviewRepository(session).list_batches()


@router.post("/templates", response_model=BatchTemplateRecord, status_code=201)
async def create_batch_template(
    request: BatchTemplateCreate,
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> BatchTemplateRecord:
    if not request.synthetic and not request.items:
        raise HTTPException(
            status_code=400,
            detail="Add at least one review or enable synthetic mode.",
        )
    if request.synthetic and request.synthetic_count <= 0:
        raise HTTPException(status_code=400, detail="Synthetic batches need a review count.")
    if not request.name.strip():
        raise HTTPException(status_code=400, detail="Batch run name is required.")
    validate_registered_forms(request, settings)
    try:
        return await ReviewRepository(session).create_batch_template(request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/templates/{template_id}", response_model=BatchTemplateRecord)
async def get_batch_template(
    template_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> BatchTemplateRecord:
    try:
        return await ReviewRepository(session).get_batch_template(template_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.put("/templates/{template_id}", response_model=BatchTemplateRecord)
async def update_batch_template(
    template_id: str,
    request: BatchTemplateUpdate,
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> BatchTemplateRecord:
    if not request.synthetic and not request.items:
        raise HTTPException(
            status_code=400,
            detail="Add at least one review or enable synthetic mode.",
        )
    if request.synthetic and request.synthetic_count <= 0:
        raise HTTPException(status_code=400, detail="Synthetic batches need a review count.")
    validate_registered_forms(request, settings)
    try:
        return await ReviewRepository(session).update_batch_template(template_id, request)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/templates/{template_id}/runs", response_model=BatchRecord, status_code=201)
async def launch_batch_template_run(
    template_id: str,
    background_tasks: BackgroundTasks,
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> BatchRecord:
    try:
        template = await ReviewRepository(session).get_batch_template(template_id)
        validate_registered_forms(
            BatchCreateRequest(
                name=template.name,
                description=template.description,
                form_id=template.form_id,
                form_version=template.form_version,
                synthetic=template.synthetic,
                synthetic_count=template.synthetic_count,
                input_mode=template.input_mode,
                excel_column_map=template.excel_column_map,
                items=template.items,
            ),
            settings,
        )
        batch = await BatchReviewGenerationService(session).create_batch_from_template(template_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    background_tasks.add_task(run_batch_job, batch.id)
    return batch


@router.post("", response_model=BatchRecord, status_code=201)
async def create_batch(
    request: BatchCreateRequest,
    background_tasks: BackgroundTasks,
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> BatchRecord:
    if not request.synthetic and not request.items:
        raise HTTPException(status_code=400, detail="Batch must include at least one item.")
    if request.synthetic and request.synthetic_count <= 0 and not request.items:
        raise HTTPException(status_code=400, detail="Synthetic batches need a review count.")
    validate_registered_forms(request, settings)
    try:
        batch = await BatchReviewGenerationService(session).create_batch(request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    background_tasks.add_task(run_batch_job, batch.id)
    return batch


@router.get("/{batch_id}", response_model=BatchRecord)
async def get_batch(
    batch_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> BatchRecord:
    try:
        return await ReviewRepository(session).get_batch(batch_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{batch_id}/pause", response_model=BatchRecord)
async def pause_batch(
    batch_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> BatchRecord:
    try:
        return await ReviewRepository(session).pause_batch(batch_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{batch_id}/resume", response_model=BatchRecord)
async def resume_batch(
    batch_id: str,
    background_tasks: BackgroundTasks,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> BatchRecord:
    try:
        batch = await ReviewRepository(session).resume_batch(batch_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if batch.status == "running":
        background_tasks.add_task(run_batch_job, batch.id)
    return batch


@router.post("/{batch_id}/retry-failed", response_model=BatchRecord)
async def retry_failed_batch_reviews(
    batch_id: str,
    background_tasks: BackgroundTasks,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> BatchRecord:
    try:
        batch = await ReviewRepository(session).retry_failed_batch_reviews(batch_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if batch.status == "running":
        background_tasks.add_task(run_batch_job, batch.id)
    return batch


@router.post("/{batch_id}/cancel", response_model=BatchRecord)
async def cancel_batch(
    batch_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> BatchRecord:
    try:
        return await ReviewRepository(session).cancel_batch(batch_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{batch_id}/reviews", response_model=list[ReviewRecord])
async def list_batch_reviews(
    batch_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[ReviewRecord]:
    try:
        await ReviewRepository(session).get_batch(batch_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return await ReviewRepository(session).list_reviews(batch_id=batch_id)
