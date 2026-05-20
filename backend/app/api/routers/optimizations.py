import asyncio
import json
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.session import get_session
from app.schemas.optimizations import (
    OptimizationCaseRecord,
    OptimizationDemoFixtureRecord,
    OptimizationRunCreate,
    OptimizationRunRecord,
)
from app.services.optimization_service import (
    OptimizationRepository,
    ensure_demo_fixture,
    run_optimization_job,
)

router = APIRouter()


@router.get("/cases", response_model=list[OptimizationCaseRecord])
async def list_optimization_cases(
    session: Annotated[AsyncSession, Depends(get_session)],
    form_id: Annotated[str, Query()],
    form_version: Annotated[str, Query()],
    search: Annotated[str, Query()] = "",
    include_demo: Annotated[bool, Query()] = True,
) -> list[OptimizationCaseRecord]:
    return await OptimizationRepository(session).list_cases(
        form_id=form_id,
        form_version=form_version,
        search=search,
        include_demo=include_demo,
    )


@router.post("/demo-fixture", response_model=OptimizationDemoFixtureRecord, status_code=201)
async def create_demo_fixture() -> OptimizationDemoFixtureRecord:
    return await ensure_demo_fixture()


@router.get("/runs", response_model=list[OptimizationRunRecord])
async def list_optimization_runs(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[OptimizationRunRecord]:
    return await OptimizationRepository(session).list_runs()


@router.post("/runs", response_model=OptimizationRunRecord, status_code=201)
async def create_optimization_run(
    request: OptimizationRunCreate,
    background_tasks: BackgroundTasks,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> OptimizationRunRecord:
    try:
        run = await OptimizationRepository(session).create_run(request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    background_tasks.add_task(run_optimization_job, run.id)
    return run


@router.get("/runs/{run_id}", response_model=OptimizationRunRecord)
async def get_optimization_run(
    run_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> OptimizationRunRecord:
    try:
        return await OptimizationRepository(session).get_run(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/runs/{run_id}/cancel", response_model=OptimizationRunRecord)
async def cancel_optimization_run(
    run_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> OptimizationRunRecord:
    try:
        return await OptimizationRepository(session).cancel_run(run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/runs/{run_id}/events")
async def stream_optimization_events(run_id: str) -> StreamingResponse:
    settings = get_settings()
    events_path = settings.optimization_runs_dir / run_id / "events.jsonl"

    async def event_stream():
        offset = 0
        idle_rounds = 0
        while True:
            if events_path.exists():
                lines = events_path.read_text(encoding="utf-8").splitlines()
                for line in lines[offset:]:
                    if not line.strip():
                        continue
                    offset += 1
                    yield f"data: {line}\n\n"
                    try:
                        payload = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if payload.get("type") in {"run_completed", "run_error"}:
                        idle_rounds = 8
                if offset >= len(lines):
                    idle_rounds += 1
            else:
                idle_rounds += 1
            if idle_rounds > 10:
                yield "event: heartbeat\ndata: {}\n\n"
                idle_rounds = 0
            await asyncio.sleep(1)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get("/runs/{run_id}/artifacts/{artifact_type}")
async def get_optimization_artifact(run_id: str, artifact_type: str) -> FileResponse:
    settings = get_settings()
    artifact_paths = {
        "dag": settings.optimization_runs_dir / run_id / "dag.json",
        "native-html": settings.optimization_runs_dir / run_id / "gepa-native.html",
        "traces": settings.optimization_runs_dir / run_id / "traces.jsonl",
        "events": settings.optimization_runs_dir / run_id / "events.jsonl",
        "final-report": settings.optimization_runs_dir / run_id / "final-report.json",
    }
    path = artifact_paths.get(artifact_type)
    if path is None:
        raise HTTPException(status_code=404, detail=f"Unknown artifact type: {artifact_type}")
    resolved = Path(path).resolve()
    root = settings.optimization_runs_dir.resolve()
    if not str(resolved).startswith(str(root)) or not resolved.exists():
        raise HTTPException(status_code=404, detail="Optimization artifact not found.")
    media_type = "text/html" if artifact_type == "native-html" else "application/json"
    if artifact_type in {"traces", "events"}:
        media_type = "application/x-ndjson"
    return FileResponse(resolved, media_type=media_type)
