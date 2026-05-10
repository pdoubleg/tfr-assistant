from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.db.models import AuditReviewORM
from app.db.session import get_session
from app.schemas.forms import AuditFormDefinition, AuditFormRegistration, AuditFormSummary
from app.services.catalog import FormCatalog
from app.services.form_extraction import extract_audit_form_from_excel

router = APIRouter()


def get_catalog(settings: Annotated[Settings, Depends(get_settings)]) -> FormCatalog:
    return FormCatalog(settings.form_catalog_dir)


async def _usage_stats_by_form(
    session: AsyncSession,
) -> dict[tuple[str, str], dict[str, object]]:
    statement = select(
        AuditReviewORM.form_id,
        AuditReviewORM.form_version,
        func.count(AuditReviewORM.id),
        func.sum(case((AuditReviewORM.status == "completed", 1), else_=0)),
        func.sum(case((AuditReviewORM.status == "failed", 1), else_=0)),
        func.max(AuditReviewORM.updated_at),
    ).group_by(AuditReviewORM.form_id, AuditReviewORM.form_version)
    rows = (await session.execute(statement)).all()
    return {
        (form_id, form_version): {
            "review_count": review_count or 0,
            "completed_count": completed_count or 0,
            "failed_count": failed_count or 0,
            "last_reviewed_at": last_reviewed_at,
        }
        for (
            form_id,
            form_version,
            review_count,
            completed_count,
            failed_count,
            last_reviewed_at,
        ) in rows
    }


@router.get("", response_model=list[AuditFormSummary])
async def list_forms(
    catalog: Annotated[FormCatalog, Depends(get_catalog)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[AuditFormSummary]:
    forms = catalog.list_forms()
    stats = await _usage_stats_by_form(session)
    return [form.model_copy(update=stats.get((form.id, form.version), {})) for form in forms]


@router.post("/extract-excel", response_model=AuditFormDefinition)
async def extract_form_from_excel(
    workbook: Annotated[UploadFile, File()],
) -> AuditFormDefinition:
    canonical = extract_audit_form_from_excel(
        await workbook.read(),
        filename=workbook.filename,
    )
    return AuditFormDefinition(
        id=canonical.form_id,
        version=canonical.form_version,
        title=canonical.title,
        description=canonical.description,
        canonical=canonical,
    )


@router.get("/{form_id}/{version}", response_model=AuditFormDefinition)
def get_form(
    form_id: str,
    version: str,
    catalog: Annotated[FormCatalog, Depends(get_catalog)],
) -> AuditFormDefinition:
    try:
        return catalog.get_form(form_id, version)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("", response_model=AuditFormDefinition, status_code=201)
def register_form(
    registration: AuditFormRegistration,
    catalog: Annotated[FormCatalog, Depends(get_catalog)],
) -> AuditFormDefinition:
    try:
        return catalog.register_form(registration)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
