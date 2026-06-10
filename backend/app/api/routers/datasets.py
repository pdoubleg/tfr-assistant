from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.schemas.datasets import (
    DatasetAddCandidatesResponse,
    DatasetAppDbAddRequest,
    DatasetAppDbBrowseRequest,
    DatasetCandidateRecord,
    DatasetCandidateReferenceUpdate,
    DatasetCandidateUpdate,
    DatasetCloneRequest,
    DatasetClusterRequest,
    DatasetClusterResult,
    DatasetPopulationCreate,
    DatasetPopulationDetail,
    DatasetPopulationRecord,
    DatasetPopulationUpdate,
    DatasetPublishRequest,
    DatasetSampleRequest,
    DatasetSampleResult,
    DatasetSourceRowRecord,
    PublishedDatasetRow,
)
from app.schemas.evaluations import EvalDatasetDetail, EvalDatasetRecord
from app.services.datasets import DatasetRepository

router = APIRouter()


@router.get("/populations", response_model=list[DatasetPopulationRecord])
async def list_dataset_populations(
    session: Annotated[AsyncSession, Depends(get_session)],
    form_id: Annotated[str | None, Query()] = None,
    form_version: Annotated[str | None, Query()] = None,
) -> list[DatasetPopulationRecord]:
    return await DatasetRepository(session).list_populations(form_id, form_version)


@router.post("/populations", response_model=DatasetPopulationRecord, status_code=201)
async def create_dataset_population(
    request: DatasetPopulationCreate,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> DatasetPopulationRecord:
    try:
        return await DatasetRepository(session).create_population(request)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch("/populations/{population_id}", response_model=DatasetPopulationRecord)
async def update_dataset_population(
    population_id: str,
    request: DatasetPopulationUpdate,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> DatasetPopulationRecord:
    try:
        return await DatasetRepository(session).update_population(population_id, request)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/populations/{population_id}", response_model=DatasetPopulationDetail)
async def get_dataset_population(
    population_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> DatasetPopulationDetail:
    try:
        return await DatasetRepository(session).get_population(population_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/app-db/browse", response_model=list[DatasetSourceRowRecord])
async def browse_app_db_dataset_source(
    request: DatasetAppDbBrowseRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
    form_id: Annotated[str, Query()],
    form_version: Annotated[str, Query()],
) -> list[DatasetSourceRowRecord]:
    return await DatasetRepository(session).browse_app_db_source(form_id, form_version, request)


@router.post(
    "/populations/{population_id}/app-db",
    response_model=DatasetAddCandidatesResponse,
)
async def add_app_db_dataset_source(
    population_id: str,
    request: DatasetAppDbAddRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> DatasetAddCandidatesResponse:
    try:
        return await DatasetRepository(session).add_app_db_source(population_id, request)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch("/candidates/{candidate_id}", response_model=DatasetCandidateRecord)
async def update_dataset_candidate(
    candidate_id: str,
    request: DatasetCandidateUpdate,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> DatasetCandidateRecord:
    try:
        return await DatasetRepository(session).update_candidate(candidate_id, request)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put(
    "/candidates/{candidate_id}/references/{reference_kind}", response_model=DatasetCandidateRecord
)
async def update_dataset_candidate_reference(
    candidate_id: str,
    reference_kind: str,
    request: DatasetCandidateReferenceUpdate,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> DatasetCandidateRecord:
    if reference_kind not in {"R1", "R2"}:
        raise HTTPException(status_code=400, detail="reference_kind must be R1 or R2.")
    try:
        return await DatasetRepository(session).update_candidate_reference(
            candidate_id,
            reference_kind,  # type: ignore[arg-type]
            request,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/populations/{population_id}/cluster", response_model=DatasetClusterResult)
async def cluster_dataset_population(
    population_id: str,
    request: DatasetClusterRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> DatasetClusterResult:
    try:
        return await DatasetRepository(session).cluster_population(population_id, request)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/populations/{population_id}/sample", response_model=DatasetSampleResult)
async def sample_dataset_population(
    population_id: str,
    request: DatasetSampleRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> DatasetSampleResult:
    try:
        return await DatasetRepository(session).sample_population(population_id, request)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/populations/{population_id}/publish", response_model=EvalDatasetDetail)
async def publish_dataset_population(
    population_id: str,
    request: DatasetPublishRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> EvalDatasetDetail:
    try:
        return await DatasetRepository(session).publish_population(population_id, request)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("", response_model=list[EvalDatasetRecord])
async def list_published_datasets(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[EvalDatasetRecord]:
    return await DatasetRepository(session).list_published_datasets()


@router.post("/{dataset_id}/clone", response_model=DatasetPopulationDetail, status_code=201)
async def clone_published_dataset(
    dataset_id: str,
    request: DatasetCloneRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> DatasetPopulationDetail:
    try:
        return await DatasetRepository(session).clone_published_dataset(dataset_id, request)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{dataset_id}", response_model=EvalDatasetDetail)
async def get_published_dataset(
    dataset_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> EvalDatasetDetail:
    try:
        return await DatasetRepository(session).get_published_dataset(dataset_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{dataset_id}/rows", response_model=list[PublishedDatasetRow])
async def list_published_dataset_rows(
    dataset_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[PublishedDatasetRow]:
    try:
        return await DatasetRepository(session).list_published_rows(dataset_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
