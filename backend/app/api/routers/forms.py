from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from app.core.config import Settings, get_settings
from app.schemas.forms import AuditFormDefinition, AuditFormRegistration, AuditFormSummary
from app.services.catalog import FormCatalog

router = APIRouter()


def get_catalog(settings: Annotated[Settings, Depends(get_settings)]) -> FormCatalog:
    return FormCatalog(settings.form_catalog_dir)


@router.get("", response_model=list[AuditFormSummary])
def list_forms(catalog: Annotated[FormCatalog, Depends(get_catalog)]) -> list[AuditFormSummary]:
    return catalog.list_forms()


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
    return catalog.register_form(registration)
