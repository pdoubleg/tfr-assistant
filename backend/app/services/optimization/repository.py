from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.models import (
    EvalCaseORM,
    EvalDatasetORM,
    EvalGroundTruthORM,
    OptimizationCandidateORM,
    OptimizationEventORM,
    OptimizationRunORM,
)
from app.models.audit import AuditFormResult
from app.schemas.optimizations import (
    OptimizationCandidateRecord,
    OptimizationCaseRecord,
    OptimizationCaseSplit,
    OptimizationEventRecord,
    OptimizationRunCreate,
    OptimizationRunRecord,
)
from app.services.catalog import FormCatalog
from app.services.optimization.artifacts import OptimizationArtifactWriter
from app.services.optimization.metrics import driver_count, issue_count
from app.services.optimization.utils import now_utc
from app.services.prompt_registry import PromptRegistryRepository


def prompt_from_case(case: EvalCaseORM) -> str:
    prompt = ""
    if isinstance(case.input_json, dict):
        prompt = str(case.input_json.get("prompt") or "").strip()
    if not prompt:
        prompt = case.instructions
    return prompt


class OptimizationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_cases(
        self,
        *,
        form_id: str,
        form_version: str,
        search: str = "",
        include_demo: bool = True,
    ) -> list[OptimizationCaseRecord]:
        statement = (
            select(EvalCaseORM, EvalDatasetORM)
            .join(EvalDatasetORM, EvalCaseORM.dataset_id == EvalDatasetORM.id)
            .where(EvalDatasetORM.form_id == form_id, EvalDatasetORM.form_version == form_version)
            .order_by(EvalDatasetORM.created_at.desc(), EvalCaseORM.created_at.asc())
        )
        rows = (await self.session.execute(statement)).all()
        records: list[OptimizationCaseRecord] = []
        query = search.strip().lower()
        for case, dataset in rows:
            if not include_demo and dataset.source_kind == "optimization_demo":
                continue
            truths = (
                await self.session.scalars(
                    select(EvalGroundTruthORM)
                    .where(EvalGroundTruthORM.case_id == case.id)
                    .order_by(EvalGroundTruthORM.reference_kind.asc())
                )
            ).all()
            if not truths:
                continue
            preferred = next((truth for truth in truths if truth.reference_kind == "R2"), truths[0])
            result = AuditFormResult.model_validate(preferred.payload_json)
            searchable = " ".join(
                [
                    dataset.name,
                    dataset.source_kind,
                    case.claim_number,
                    case.effective_date or "",
                    case.instructions,
                    result.overall_outcome,
                ]
            ).lower()
            if query and query not in searchable:
                continue
            records.append(
                OptimizationCaseRecord(
                    case_id=case.id,
                    dataset_id=dataset.id,
                    dataset_name=dataset.name,
                    source_kind=dataset.source_kind,
                    claim_number=case.claim_number,
                    effective_date=case.effective_date,
                    instructions=case.instructions,
                    outcome=result.overall_outcome,
                    issue_count=issue_count(result),
                    driver_count=driver_count(result),
                    reference_kinds=[truth.reference_kind for truth in truths],
                    created_at=case.created_at,
                )
            )
        return records

    async def create_run(self, request: OptimizationRunCreate) -> OptimizationRunRecord:
        catalog = FormCatalog(get_settings().form_catalog_dir)
        try:
            catalog.get_form(request.form_id, request.form_version)
        except KeyError as exc:
            raise ValueError(f"Unknown form {request.form_id}@{request.form_version}") from exc
        if request.seed_instruction_source == "prompt_registry" and request.seed_prompt_ref:
            resolved = await PromptRegistryRepository(self.session, catalog).resolve(
                request.seed_prompt_ref,
                form_id=request.form_id,
                form_version=request.form_version,
            )
            request = request.model_copy(update={"resolved_seed_prompt": resolved})
        case_ids = [item.case_id for item in request.case_splits]
        cases = (
            await self.session.scalars(select(EvalCaseORM).where(EvalCaseORM.id.in_(case_ids)))
        ).all()
        existing_case_ids = {case.id for case in cases}
        missing = sorted(set(case_ids) - existing_case_ids)
        if missing:
            raise ValueError(f"Unknown optimization case ids: {', '.join(missing)}")

        split_counts = {"train": 0, "val": 0, "test": 0}
        for item in request.case_splits:
            split_counts[item.split] += 1
        run = OptimizationRunORM(
            id=str(uuid4()),
            name=request.name.strip(),
            status="queued",
            form_id=request.form_id,
            form_version=request.form_version,
            config_json=request.model_dump(mode="json"),
            split_json=[item.model_dump(mode="json") for item in request.case_splits],
            total_count=len(request.case_splits),
            train_count=split_counts["train"],
            val_count=split_counts["val"],
            test_count=split_counts["test"],
            total_metric_calls=0,
            created_at=now_utc(),
            updated_at=now_utc(),
        )
        self.session.add(run)
        await self.session.commit()
        await self.session.refresh(run)
        return await self._run_to_schema(run, include_children=False)

    async def list_runs(self) -> list[OptimizationRunRecord]:
        runs = (
            await self.session.scalars(
                select(OptimizationRunORM).order_by(OptimizationRunORM.created_at.desc())
            )
        ).all()
        return [await self._run_to_schema(run, include_children=False) for run in runs]

    async def get_run(self, run_id: str) -> OptimizationRunRecord:
        run = await self._get_run(run_id)
        return await self._run_to_schema(run, include_children=True)

    async def cancel_run(self, run_id: str) -> OptimizationRunRecord:
        run = await self._get_run(run_id)
        artifacts = run.artifacts_json or {}
        run_dir = Path(
            str(artifacts.get("run_dir") or get_settings().optimization_runs_dir / run.id)
        )
        OptimizationArtifactWriter(run.id, run_dir.parent).request_cancel()
        if run.status in {"queued", "running"}:
            run.status = "canceled"
            run.completed_at = run.completed_at or now_utc()
            run.updated_at = now_utc()
            self.session.add(run)
            await self.session.commit()
            await self.session.refresh(run)
        return await self._run_to_schema(run, include_children=True)

    async def _get_run(self, run_id: str) -> OptimizationRunORM:
        run = await self.session.get(OptimizationRunORM, run_id)
        if not run:
            raise KeyError(f"Unknown optimization run: {run_id}")
        return run

    async def _run_to_schema(
        self,
        run: OptimizationRunORM,
        *,
        include_children: bool,
    ) -> OptimizationRunRecord:
        candidates: list[OptimizationCandidateRecord] = []
        events: list[OptimizationEventRecord] = []
        if include_children:
            candidate_rows = (
                await self.session.scalars(
                    select(OptimizationCandidateORM)
                    .where(OptimizationCandidateORM.run_id == run.id)
                    .order_by(OptimizationCandidateORM.candidate_index.asc())
                )
            ).all()
            candidates = [
                OptimizationCandidateRecord(
                    id=row.id,
                    run_id=row.run_id,
                    candidate_index=row.candidate_index,
                    parent_indices=row.parent_indices_json,
                    status=row.status,
                    candidate=row.candidate_json,
                    score=row.score,
                    metrics=row.metrics_json or {},
                    created_at=row.created_at,
                )
                for row in candidate_rows
            ]
            event_rows = (
                await self.session.scalars(
                    select(OptimizationEventORM)
                    .where(OptimizationEventORM.run_id == run.id)
                    .order_by(OptimizationEventORM.sequence.asc())
                )
            ).all()
            events = [
                OptimizationEventRecord(
                    id=row.id,
                    run_id=row.run_id,
                    sequence=row.sequence,
                    type=row.event_type,
                    message=str(row.payload_json.get("message") or ""),
                    iteration=row.payload_json.get("iteration"),
                    level=str(row.payload_json.get("level") or "info"),
                    data=row.payload_json.get("data") or {},
                    created_at=row.created_at,
                )
                for row in event_rows
            ]
        return OptimizationRunRecord(
            id=run.id,
            name=run.name,
            status=run.status,  # type: ignore[arg-type]
            form_id=run.form_id,
            form_version=run.form_version,
            config=run.config_json or {},
            case_splits=[
                OptimizationCaseSplit.model_validate(item) for item in run.split_json or []
            ],
            seed_candidate=run.seed_candidate_json,
            best_candidate=run.best_candidate_json,
            metrics=run.metrics_json or {},
            artifacts=run.artifacts_json or {},
            token_usage=run.token_usage_json or {},
            total_count=run.total_count,
            train_count=run.train_count,
            val_count=run.val_count,
            test_count=run.test_count,
            best_score=run.best_score,
            original_score=run.original_score,
            total_metric_calls=run.total_metric_calls,
            error_message=run.error_message,
            started_at=run.started_at,
            completed_at=run.completed_at,
            created_at=run.created_at,
            updated_at=run.updated_at,
            candidates=candidates,
            events=events,
        )
