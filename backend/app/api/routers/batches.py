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
    IntakeDocumentRecord,
    ReviewRecord,
)
from app.services.audit_generation import BatchReviewGenerationService, run_batch_job
from app.services.catalog import FormCatalog
from app.services.intake_documents import IntakeDocumentStore
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
        if item.form_id and item.form_id != request.form_id:
            raise HTTPException(
                status_code=400,
                detail=f"Review row {index} uses {item.form_id}, but batches must use one form.",
            )
        if item.form_version and item.form_version != request.form_version:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Review row {index} uses {item.form_version}, "
                    "but batches must use one form version."
                ),
            )
        if request.input_mode == "completed_intake" and len(item.source_file_ids) != 1:
            raise HTTPException(
                status_code=400,
                detail="Completed intake reviews require exactly one selected document.",
            )
        if request.input_mode == "manual_entry":
            if item.manual_result is None:
                raise HTTPException(
                    status_code=400,
                    detail=f"Manual entry row {index} needs a completed audit form.",
                )
            if item.manual_result.form_id != request.form_id:
                raise HTTPException(
                    status_code=400,
                    detail=f"Manual entry row {index} uses a different form.",
                )
            if item.manual_result.form_version != request.form_version:
                raise HTTPException(
                    status_code=400,
                    detail=f"Manual entry row {index} uses a different form version.",
                )


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


@router.get("/intake-documents", response_model=list[IntakeDocumentRecord])
async def list_intake_documents(
    settings: Annotated[Settings, Depends(get_settings)],
) -> list[IntakeDocumentRecord]:
    return IntakeDocumentStore(settings).list_documents()


@router.post("/templates", response_model=BatchTemplateRecord, status_code=201)
async def create_batch_template(
    request: BatchTemplateCreate,
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> BatchTemplateRecord:
    synthetic = request.synthetic or request.input_mode == "synthetic"
    if not synthetic and not request.items:
        raise HTTPException(
            status_code=400,
            detail="Add at least one review or enable synthetic mode.",
        )
    if synthetic and request.synthetic_count <= 0:
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
    synthetic = request.synthetic or request.input_mode == "synthetic"
    if not synthetic and not request.items:
        raise HTTPException(
            status_code=400,
            detail="Add at least one review or enable synthetic mode.",
        )
    if synthetic and request.synthetic_count <= 0:
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
                generation_prompt=template.generation_prompt,
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
    synthetic = request.synthetic or request.input_mode == "synthetic"
    if not synthetic and not request.items:
        raise HTTPException(status_code=400, detail="Batch must include at least one item.")
    if synthetic and request.synthetic_count <= 0 and not request.items:
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
