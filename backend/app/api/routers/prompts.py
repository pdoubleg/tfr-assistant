from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.db.session import get_session
from app.schemas.prompts import (
    OptimizationCandidatePromotion,
    PromptAliasRecord,
    PromptAliasUpdate,
    PromptFamilyRecord,
    PromptReference,
    PromptVersionCreate,
    PromptVersionRecord,
    ResolvedPrompt,
)
from app.services.catalog import FormCatalog
from app.services.prompt_registry import PromptRegistryRepository

router = APIRouter()


def _repository(session: AsyncSession, settings: Settings) -> PromptRegistryRepository:
    return PromptRegistryRepository(session, FormCatalog(settings.form_catalog_dir))


@router.get("/forms/{form_id}/families", response_model=list[PromptFamilyRecord])
async def list_form_prompt_families(
    form_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    form_version: Annotated[str | None, Query()] = None,
) -> list[PromptFamilyRecord]:
    try:
        return await _repository(session, settings).list_form_families(
            form_id,
            form_version=form_version,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post(
    "/forms/{form_id}/{form_version}/bootstrap",
    response_model=PromptFamilyRecord,
    status_code=201,
)
async def bootstrap_form_prompt_family(
    form_id: str,
    form_version: str,
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> PromptFamilyRecord:
    try:
        return await _repository(session, settings).bootstrap_form_prompt(
            form_id,
            form_version,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/versions", response_model=PromptVersionRecord, status_code=201)
async def create_prompt_version(
    request: PromptVersionCreate,
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> PromptVersionRecord:
    try:
        return await _repository(session, settings).create_version(request)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/aliases", response_model=PromptAliasRecord)
async def set_prompt_alias(
    request: PromptAliasUpdate,
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> PromptAliasRecord:
    try:
        return await _repository(session, settings).set_alias(request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/promote-optimization-candidate", response_model=PromptVersionRecord, status_code=201)
async def promote_optimization_candidate(
    request: OptimizationCandidatePromotion,
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> PromptVersionRecord:
    try:
        return await _repository(session, settings).promote_optimization_candidate(request)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/resolve", response_model=ResolvedPrompt)
async def resolve_prompt(
    ref: PromptReference,
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    form_id: Annotated[str, Query()],
    form_version: Annotated[str, Query()],
) -> ResolvedPrompt:
    try:
        return await _repository(session, settings).resolve(
            ref,
            form_id=form_id,
            form_version=form_version,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
