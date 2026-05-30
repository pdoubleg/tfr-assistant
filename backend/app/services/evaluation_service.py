import asyncio
import hashlib
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pandas as pd
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.db.models import (
    EvalAgreementItemORM,
    EvalCaseORM,
    EvalComparisonORM,
    EvalDatasetORM,
    EvalGroundTruthORM,
    EvalRunItemORM,
    EvalRunORM,
)
from app.db.session import AsyncSessionLocal
from app.models.audit import AuditResult, parse_audit_result
from app.schemas.evaluations import (
    EvalAgreementItemRecord,
    EvalCaseCreate,
    EvalCaseRecord,
    EvalComparisonRecord,
    EvalDatasetCreate,
    EvalDatasetDetail,
    EvalDatasetRecord,
    EvalGroundTruthRecord,
    EvalRunCreate,
    EvalRunItemRecord,
    EvalRunRecord,
)
from app.schemas.prompts import PromptReference
from app.schemas.reviews import ReviewGenerateRequest
from app.services.audit_generation import AuditGenerationService
from app.services.catalog import FormCatalog
from app.services.evaluation_metrics import (
    aggregate_comparison_metrics,
    compare_audit_results,
    comparison_metrics_to_row,
    comparison_result_to_agreement_items,
)
from app.services.review_repository import ReviewRepository


def _now() -> datetime:
    return datetime.now(UTC)


def _json_hash(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode(
        "utf-8"
    )
    return hashlib.sha256(encoded).hexdigest()


def _payload_for(result: AuditResult) -> dict[str, Any]:
    return result.model_dump(mode="json")


def _duration_seconds(started_at: datetime | None, completed_at: datetime | None) -> float | None:
    if not started_at or not completed_at:
        return None
    return max(0.0, (completed_at - started_at).total_seconds())


class EvaluationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_dataset(self, request: EvalDatasetCreate) -> EvalDatasetDetail:
        if not request.cases:
            raise ValueError("Evaluation dataset must include at least one case.")
        form_kind = self._ensure_registered_form(request.form_id, request.form_version)

        dataset = EvalDatasetORM(
            id=str(uuid4()),
            name=request.name.strip(),
            description=request.description.strip(),
            form_id=request.form_id,
            form_version=request.form_version,
            form_kind=form_kind,
            source_kind=request.source_kind,
            source_metadata_json=request.source_metadata,
            dataset_hash=_json_hash(request.model_dump(mode="json")),
        )
        self.session.add(dataset)
        await self.session.flush()

        for case_request in request.cases:
            self._validate_case_ground_truths(
                case_request,
                request.form_id,
                request.form_version,
                form_kind,
            )
            case = EvalCaseORM(
                id=str(uuid4()),
                dataset_id=dataset.id,
                claim_number=case_request.claim_number.strip(),
                effective_date=case_request.effective_date,
                instructions=case_request.instructions.strip(),
                input_json=case_request.input,
            )
            self.session.add(case)
            await self.session.flush()
            for truth_request in case_request.ground_truths:
                self.session.add(
                    EvalGroundTruthORM(
                        id=str(uuid4()),
                        case_id=case.id,
                        reference_kind=truth_request.reference_kind,
                        payload_json=_payload_for(truth_request.result),
                        reviewer=truth_request.reviewer,
                        source_metadata_json=truth_request.source_metadata,
                    )
                )

        await self.session.commit()
        return await self.get_dataset(dataset.id)

    async def list_datasets(self) -> list[EvalDatasetRecord]:
        records = (
            await self.session.scalars(
                select(EvalDatasetORM).order_by(EvalDatasetORM.updated_at.desc())
            )
        ).all()
        return [await self._dataset_to_schema(record) for record in records]

    async def get_dataset(self, dataset_id: str) -> EvalDatasetDetail:
        dataset = await self._get_dataset_orm(dataset_id)
        base = await self._dataset_to_schema(dataset)
        cases = (
            await self.session.scalars(
                select(EvalCaseORM)
                .where(EvalCaseORM.dataset_id == dataset.id)
                .order_by(EvalCaseORM.created_at.asc())
            )
        ).all()
        return EvalDatasetDetail(
            **base.model_dump(),
            cases=[await self._case_to_schema(case) for case in cases],
        )

    async def create_run(self, request: EvalRunCreate) -> EvalRunRecord:
        dataset = await self._get_dataset_orm(request.dataset_id)
        base_run = await self._get_run_orm(request.base_run_id) if request.base_run_id else None
        cases = (
            await self.session.scalars(
                select(EvalCaseORM)
                .where(EvalCaseORM.dataset_id == dataset.id)
                .order_by(EvalCaseORM.created_at.asc())
            )
        ).all()
        if not cases:
            raise ValueError("Evaluation dataset does not include any cases.")
        run_id = str(uuid4())
        lineage_id = base_run.lineage_id or base_run.id if base_run else run_id
        config_version = await self._next_config_version(lineage_id) if base_run else 1

        run = EvalRunORM(
            id=run_id,
            dataset_id=dataset.id,
            form_kind=dataset.form_kind,
            lineage_id=lineage_id,
            source_run_id=base_run.id if base_run else None,
            config_version=config_version,
            name=request.name.strip(),
            status="queued",
            model_name=request.model_name.strip() or get_settings().audit_model,
            reference_policy=request.reference_policy,
            concurrency=request.concurrency,
            retry_limit=request.retry_limit,
            enable_mlflow=request.enable_mlflow,
            total_count=len(cases),
            input_json=request.model_dump(mode="json"),
        )
        self.session.add(run)
        await self.session.flush()
        for case in cases:
            self.session.add(
                EvalRunItemORM(
                    id=str(uuid4()),
                    run_id=run.id,
                    case_id=case.id,
                    status="queued",
                )
            )
        await self.session.commit()
        return await self.get_run(run.id)

    async def list_runs(self) -> list[EvalRunRecord]:
        runs = (
            await self.session.scalars(select(EvalRunORM).order_by(EvalRunORM.created_at.desc()))
        ).all()
        return [await self._run_to_schema(run) for run in runs]

    async def get_run(self, run_id: str) -> EvalRunRecord:
        run = await self._get_run_orm(run_id)
        await self.refresh_run_counts(run.id)
        await self.session.refresh(run)
        return await self._run_to_schema(run)

    async def list_run_items(self, run_id: str) -> list[EvalRunItemRecord]:
        await self._get_run_orm(run_id)
        items = (
            await self.session.scalars(
                select(EvalRunItemORM)
                .where(EvalRunItemORM.run_id == run_id)
                .order_by(EvalRunItemORM.created_at.asc())
            )
        ).all()
        return [await self._run_item_to_schema(item) for item in items]

    async def mark_run_running(self, run_id: str) -> EvalRunRecord:
        run = await self._get_run_orm(run_id)
        if run.status in {"completed", "canceled"}:
            return await self._run_to_schema(run)
        run.status = "running"
        run.started_at = run.started_at or _now()
        run.completed_at = None
        run.error_message = None
        run.updated_at = _now()
        await self.session.commit()
        await self.session.refresh(run)
        return await self._run_to_schema(run)

    async def pause_run(self, run_id: str) -> EvalRunRecord:
        run = await self._get_run_orm(run_id)
        if run.status not in {"completed", "failed", "canceled"}:
            run.status = "paused"
            run.updated_at = _now()
            await self.session.commit()
            await self.session.refresh(run)
        return await self._run_to_schema(run)

    async def resume_run(self, run_id: str) -> EvalRunRecord:
        run = await self._get_run_orm(run_id)
        if run.status in {"completed", "canceled"}:
            return await self._run_to_schema(run)
        run.status = "running"
        run.started_at = run.started_at or _now()
        run.completed_at = None
        run.updated_at = _now()
        await self.session.commit()
        await self.session.refresh(run)
        return await self._run_to_schema(run)

    async def cancel_run(self, run_id: str) -> EvalRunRecord:
        run = await self._get_run_orm(run_id)
        if run.status != "completed":
            run.status = "canceled"
            run.completed_at = run.completed_at or _now()
            run.updated_at = _now()
            await self.session.commit()
            await self.session.refresh(run)
        return await self._run_to_schema(run)

    async def refresh_run_counts(self, run_id: str) -> EvalRunRecord:
        run = await self._get_run_orm(run_id)
        total = await self._count_items(run_id)
        completed = await self._count_items(run_id, "completed")
        failed = await self._count_items(run_id, "failed")
        running = await self._count_items(run_id, "running")
        queued = await self._count_items(run_id, "queued")
        run.total_count = total
        run.completed_count = completed
        run.failed_count = failed

        if run.status != "canceled":
            if total and completed + failed >= total:
                run.status = "failed" if failed else "completed"
                run.completed_at = run.completed_at or _now()
            elif run.status == "paused":
                run.completed_at = None
            elif running:
                run.status = "running"
                run.started_at = run.started_at or _now()
                run.completed_at = None
            elif queued:
                run.status = "running" if run.started_at else "queued"
                run.completed_at = None
        run.updated_at = _now()
        await self.session.commit()
        await self.session.refresh(run)
        # Attach computed counts in _run_to_schema; queued/running are not stored columns.
        return await self._run_to_schema(run)

    async def mark_item_running(self, item_id: str) -> EvalRunItemORM:
        item = await self._get_run_item_orm(item_id)
        item.status = "running"
        item.attempt_count += 1
        item.error_message = None
        item.started_at = item.started_at or _now()
        item.completed_at = None
        item.updated_at = _now()
        await self.session.commit()
        await self.session.refresh(item)
        return item

    async def complete_item(
        self,
        item_id: str,
        *,
        generated_review_id: str,
        generated_result: AuditResult,
        comparisons: list[tuple[EvalGroundTruthORM, AuditResult, dict[str, Any]]],
    ) -> EvalRunItemRecord:
        item = await self._get_run_item_orm(item_id)
        await self.session.execute(
            delete(EvalAgreementItemORM).where(EvalAgreementItemORM.run_item_id == item.id)
        )
        await self.session.execute(
            delete(EvalComparisonORM).where(EvalComparisonORM.run_item_id == item.id)
        )
        item.generated_review_id = generated_review_id
        item.status = "completed"
        item.error_message = None
        item.completed_at = _now()
        item.updated_at = _now()
        for truth, reference_result, metrics in comparisons:
            comparison = EvalComparisonORM(
                id=str(uuid4()),
                run_id=item.run_id,
                run_item_id=item.id,
                case_id=item.case_id,
                ground_truth_id=truth.id,
                reference_kind=truth.reference_kind,
                form_kind=metrics.get("form_kind", generated_result.form_kind),
                score=metrics.get("score"),
                metrics_json=metrics,
            )
            self.session.add(comparison)
            await self.session.flush()
            for agreement_item in comparison_result_to_agreement_items(
                metrics,
                generated_result,
                reference_result,
            ):
                self.session.add(
                    EvalAgreementItemORM(
                        id=str(uuid4()),
                        run_id=item.run_id,
                        run_item_id=item.id,
                        case_id=item.case_id,
                        ground_truth_id=truth.id,
                        comparison_id=comparison.id,
                        reference_kind=truth.reference_kind,
                        **agreement_item,
                    )
                )
        await self.session.flush()
        await self._save_run_aggregate_metrics(item.run_id)
        await self.session.commit()
        await self.refresh_run_counts(item.run_id)
        await self.session.refresh(item)
        return await self._run_item_to_schema(item)

    async def _save_run_aggregate_metrics(self, run_id: str) -> None:
        run = await self._get_run_orm(run_id)
        comparisons = (
            await self.session.scalars(
                select(EvalComparisonORM)
                .where(EvalComparisonORM.run_id == run_id)
                .order_by(EvalComparisonORM.created_at.asc())
            )
        ).all()
        rows = [
            comparison_metrics_to_row(comparison.metrics_json, comparison.reference_kind)
            for comparison in comparisons
        ]
        run.metrics_json = aggregate_comparison_metrics(pd.DataFrame(rows)) if rows else {}
        run.updated_at = _now()
        self.session.add(run)

    async def fail_item(self, item_id: str, message: str) -> EvalRunItemRecord:
        item = await self._get_run_item_orm(item_id)
        item.status = "failed"
        item.error_message = message
        item.completed_at = _now()
        item.updated_at = _now()
        await self.session.commit()
        await self.refresh_run_counts(item.run_id)
        await self.session.refresh(item)
        return await self._run_item_to_schema(item)

    async def mark_run_failed(self, run_id: str, message: str) -> EvalRunRecord:
        run = await self._get_run_orm(run_id)
        run.status = "failed"
        run.error_message = message
        run.completed_at = _now()
        run.updated_at = _now()
        await self.session.commit()
        await self.session.refresh(run)
        return await self._run_to_schema(run)

    async def queued_items_for_run(self, run_id: str) -> list[EvalRunItemRecord]:
        items = (
            await self.session.scalars(
                select(EvalRunItemORM)
                .where(EvalRunItemORM.run_id == run_id, EvalRunItemORM.status == "queued")
                .order_by(EvalRunItemORM.created_at.asc())
            )
        ).all()
        return [await self._run_item_to_schema(item) for item in items]

    async def case_for_item(self, item_id: str) -> EvalCaseRecord:
        item = await self._get_run_item_orm(item_id)
        case = await self._get_case_orm(item.case_id)
        return await self._case_to_schema(case)

    async def run_snapshot(self, run_id: str) -> EvalRunORM:
        return await self._get_run_orm(run_id)

    async def ground_truths_for_case(self, case_id: str) -> list[EvalGroundTruthORM]:
        return (
            await self.session.scalars(
                select(EvalGroundTruthORM)
                .where(EvalGroundTruthORM.case_id == case_id)
                .order_by(EvalGroundTruthORM.reference_kind.asc())
            )
        ).all()

    async def _dataset_to_schema(self, dataset: EvalDatasetORM) -> EvalDatasetRecord:
        case_count = await self.session.scalar(
            select(func.count(EvalCaseORM.id)).where(EvalCaseORM.dataset_id == dataset.id)
        )
        r1_count = await self._truth_count(dataset.id, "R1")
        r2_count = await self._truth_count(dataset.id, "R2")
        return EvalDatasetRecord(
            id=dataset.id,
            name=dataset.name,
            description=dataset.description,
            form_id=dataset.form_id,
            form_version=dataset.form_version,
            form_kind=dataset.form_kind,  # type: ignore[arg-type]
            source_kind=dataset.source_kind,
            source_metadata=dataset.source_metadata_json,
            dataset_hash=dataset.dataset_hash,
            case_count=case_count or 0,
            r1_count=r1_count,
            r2_count=r2_count,
            created_at=dataset.created_at,
            updated_at=dataset.updated_at,
        )

    async def _case_to_schema(self, case: EvalCaseORM) -> EvalCaseRecord:
        truths = (
            await self.session.scalars(
                select(EvalGroundTruthORM)
                .where(EvalGroundTruthORM.case_id == case.id)
                .order_by(EvalGroundTruthORM.reference_kind.asc())
            )
        ).all()
        return EvalCaseRecord(
            id=case.id,
            dataset_id=case.dataset_id,
            claim_number=case.claim_number,
            effective_date=case.effective_date,
            instructions=case.instructions,
            input=case.input_json or {},
            ground_truths=[self._ground_truth_to_schema(truth) for truth in truths],
            created_at=case.created_at,
            updated_at=case.updated_at,
        )

    async def _run_to_schema(self, run: EvalRunORM) -> EvalRunRecord:
        dataset = await self._get_dataset_orm(run.dataset_id)
        running = await self._count_items(run.id, "running")
        queued = await self._count_items(run.id, "queued")
        total = run.total_count or await self._count_items(run.id)
        completed = run.completed_count
        failed = run.failed_count
        progress_percent = round(((completed + failed) / total) * 100, 1) if total else 0
        primary_score = await self._primary_score_for_run(run)
        return EvalRunRecord(
            id=run.id,
            dataset_id=run.dataset_id,
            dataset_name=dataset.name,
            form_kind=run.form_kind,  # type: ignore[arg-type]
            lineage_id=run.lineage_id or run.id,
            source_run_id=run.source_run_id,
            config_version=run.config_version or 1,
            name=run.name,
            status=run.status,  # type: ignore[arg-type]
            model_name=run.model_name,
            reference_policy=run.reference_policy,  # type: ignore[arg-type]
            concurrency=run.concurrency,
            retry_limit=run.retry_limit,
            enable_mlflow=run.enable_mlflow,
            prompt_ref=PromptReference.model_validate(run.input_json["prompt_ref"])
            if (run.input_json or {}).get("prompt_ref")
            else None,
            mlflow_run_id=run.mlflow_run_id,
            total_count=total,
            completed_count=completed,
            failed_count=failed,
            running_count=running,
            queued_count=queued,
            progress_percent=progress_percent,
            primary_score=primary_score,
            metrics=run.metrics_json or {},
            input=run.input_json or {},
            error_message=run.error_message,
            started_at=run.started_at,
            completed_at=run.completed_at,
            duration_seconds=_duration_seconds(run.started_at, run.completed_at),
            created_at=run.created_at,
            updated_at=run.updated_at,
        )

    async def _run_item_to_schema(self, item: EvalRunItemORM) -> EvalRunItemRecord:
        case = await self._get_case_orm(item.case_id)
        case_schema = await self._case_to_schema(case)
        generated_result = None
        if item.generated_review_id:
            try:
                review = await ReviewRepository(self.session).get_review(item.generated_review_id)
                generated_result = review.original
            except KeyError:
                generated_result = None
        comparisons = (
            await self.session.scalars(
                select(EvalComparisonORM)
                .where(EvalComparisonORM.run_item_id == item.id)
                .order_by(EvalComparisonORM.reference_kind.asc())
            )
        ).all()
        agreement_items = (
            await self.session.scalars(
                select(EvalAgreementItemORM)
                .where(EvalAgreementItemORM.run_item_id == item.id)
                .order_by(
                    EvalAgreementItemORM.reference_kind.asc(),
                    EvalAgreementItemORM.level.asc(),
                    EvalAgreementItemORM.question_id.asc(),
                    EvalAgreementItemORM.subquestion_id.asc(),
                )
            )
        ).all()
        agreement_items_by_comparison: dict[str, list[EvalAgreementItemORM]] = {}
        for agreement_item in agreement_items:
            agreement_items_by_comparison.setdefault(agreement_item.comparison_id, []).append(
                agreement_item
            )
        return EvalRunItemRecord(
            id=item.id,
            run_id=item.run_id,
            case_id=item.case_id,
            claim_number=case.claim_number,
            effective_date=case.effective_date,
            status=item.status,  # type: ignore[arg-type]
            attempt_count=item.attempt_count,
            generated_review_id=item.generated_review_id,
            generated_result=generated_result,
            ground_truths=case_schema.ground_truths,
            error_message=item.error_message,
            comparisons=[
                self._comparison_to_schema(
                    comparison,
                    agreement_items_by_comparison.get(comparison.id, []),
                )
                for comparison in comparisons
            ],
            started_at=item.started_at,
            completed_at=item.completed_at,
            created_at=item.created_at,
            updated_at=item.updated_at,
        )

    def _ground_truth_to_schema(self, truth: EvalGroundTruthORM) -> EvalGroundTruthRecord:
        return EvalGroundTruthRecord(
            id=truth.id,
            case_id=truth.case_id,
            reference_kind=truth.reference_kind,  # type: ignore[arg-type]
            result=parse_audit_result(truth.payload_json),
            reviewer=truth.reviewer,
            source_metadata=truth.source_metadata_json,
            created_at=truth.created_at,
        )

    def _agreement_item_to_schema(
        self,
        agreement_item: EvalAgreementItemORM,
    ) -> EvalAgreementItemRecord:
        return EvalAgreementItemRecord(
            id=agreement_item.id,
            run_id=agreement_item.run_id,
            run_item_id=agreement_item.run_item_id,
            case_id=agreement_item.case_id,
            ground_truth_id=agreement_item.ground_truth_id,
            comparison_id=agreement_item.comparison_id,
            reference_kind=agreement_item.reference_kind,  # type: ignore[arg-type]
            form_kind=agreement_item.form_kind,  # type: ignore[arg-type]
            level=agreement_item.level,  # type: ignore[arg-type]
            question_id=agreement_item.question_id,
            subquestion_id=agreement_item.subquestion_id,
            question_text=agreement_item.question_text,
            subquestion_text=agreement_item.subquestion_text,
            generated_answer=agreement_item.generated_answer,
            reference_answer=agreement_item.reference_answer,
            matched=agreement_item.matched,
            agreement=agreement_item.agreement,
            generated_comment=agreement_item.generated_comment,
            reference_comment=agreement_item.reference_comment,
            generated_citations=agreement_item.generated_citations,
            reference_citations=agreement_item.reference_citations,
            generated_overwrite_dollars=float(agreement_item.generated_overwrite_dollars)
            if agreement_item.generated_overwrite_dollars is not None
            else None,
            reference_overwrite_dollars=float(agreement_item.reference_overwrite_dollars)
            if agreement_item.reference_overwrite_dollars is not None
            else None,
            generated_underwrite_dollars=float(agreement_item.generated_underwrite_dollars)
            if agreement_item.generated_underwrite_dollars is not None
            else None,
            reference_underwrite_dollars=float(agreement_item.reference_underwrite_dollars)
            if agreement_item.reference_underwrite_dollars is not None
            else None,
            overwrite_dollar_error=float(agreement_item.overwrite_dollar_error)
            if agreement_item.overwrite_dollar_error is not None
            else None,
            underwrite_dollar_error=float(agreement_item.underwrite_dollar_error)
            if agreement_item.underwrite_dollar_error is not None
            else None,
            created_at=agreement_item.created_at,
        )

    def _comparison_to_schema(
        self,
        comparison: EvalComparisonORM,
        agreement_items: list[EvalAgreementItemORM],
    ) -> EvalComparisonRecord:
        return EvalComparisonRecord(
            id=comparison.id,
            run_id=comparison.run_id,
            run_item_id=comparison.run_item_id,
            case_id=comparison.case_id,
            ground_truth_id=comparison.ground_truth_id,
            reference_kind=comparison.reference_kind,  # type: ignore[arg-type]
            form_kind=comparison.form_kind,  # type: ignore[arg-type]
            score=comparison.score,
            metrics=comparison.metrics_json,
            agreement_items=[
                self._agreement_item_to_schema(agreement_item) for agreement_item in agreement_items
            ],
            created_at=comparison.created_at,
        )

    async def _primary_score_for_run(self, run: EvalRunORM) -> float | None:
        comparisons = (
            await self.session.scalars(
                select(EvalComparisonORM)
                .where(EvalComparisonORM.run_id == run.id)
                .order_by(EvalComparisonORM.created_at.asc())
            )
        ).all()
        if not comparisons:
            return None
        by_item: dict[str, list[EvalComparisonORM]] = {}
        for comparison in comparisons:
            by_item.setdefault(comparison.run_item_id, []).append(comparison)
        scores: list[float] = []
        for item_comparisons in by_item.values():
            if run.reference_policy == "all":
                scores.extend(
                    comparison.score
                    for comparison in item_comparisons
                    if comparison.score is not None
                )
                continue
            selected = self._select_primary_comparison(item_comparisons, run.reference_policy)
            if selected and selected.score is not None:
                scores.append(selected.score)
        if not scores:
            return None
        return round(sum(scores) / len(scores), 4)

    def _select_primary_comparison(
        self,
        comparisons: list[EvalComparisonORM],
        policy: str,
    ) -> EvalComparisonORM | None:
        if policy == "r1":
            return next(
                (comparison for comparison in comparisons if comparison.reference_kind == "R1"),
                None,
            )
        if policy == "r2":
            return next(
                (comparison for comparison in comparisons if comparison.reference_kind == "R2"),
                None,
            )
        return next(
            (comparison for comparison in comparisons if comparison.reference_kind == "R2"),
            None,
        ) or next(
            (comparison for comparison in comparisons if comparison.reference_kind == "R1"),
            None,
        )

    async def _truth_count(self, dataset_id: str, reference_kind: str) -> int:
        statement = (
            select(func.count(EvalGroundTruthORM.id))
            .join(EvalCaseORM, EvalGroundTruthORM.case_id == EvalCaseORM.id)
            .where(
                EvalCaseORM.dataset_id == dataset_id,
                EvalGroundTruthORM.reference_kind == reference_kind,
            )
        )
        return await self.session.scalar(statement) or 0

    async def _count_items(self, run_id: str, status: str | None = None) -> int:
        statement = select(func.count(EvalRunItemORM.id)).where(EvalRunItemORM.run_id == run_id)
        if status:
            statement = statement.where(EvalRunItemORM.status == status)
        return await self.session.scalar(statement) or 0

    async def _next_config_version(self, lineage_id: str) -> int:
        statement = select(func.max(EvalRunORM.config_version)).where(
            EvalRunORM.lineage_id == lineage_id
        )
        return (await self.session.scalar(statement) or 1) + 1

    async def _get_dataset_orm(self, dataset_id: str) -> EvalDatasetORM:
        dataset = await self.session.get(EvalDatasetORM, dataset_id)
        if not dataset:
            raise KeyError(f"Unknown evaluation dataset: {dataset_id}")
        return dataset

    async def _get_case_orm(self, case_id: str) -> EvalCaseORM:
        case = await self.session.get(EvalCaseORM, case_id)
        if not case:
            raise KeyError(f"Unknown evaluation case: {case_id}")
        return case

    async def _get_run_orm(self, run_id: str) -> EvalRunORM:
        run = await self.session.get(EvalRunORM, run_id)
        if not run:
            raise KeyError(f"Unknown evaluation run: {run_id}")
        return run

    async def _get_run_item_orm(self, item_id: str) -> EvalRunItemORM:
        item = await self.session.get(EvalRunItemORM, item_id)
        if not item:
            raise KeyError(f"Unknown evaluation run item: {item_id}")
        return item

    def _ensure_registered_form(self, form_id: str, form_version: str) -> str:
        try:
            return FormCatalog(get_settings().form_catalog_dir).get_form(
                form_id,
                form_version,
            ).form_kind
        except KeyError as exc:
            raise ValueError(
                f"Registered form {form_id}@{form_version} was not found in the form catalog."
            ) from exc

    def _validate_case_ground_truths(
        self,
        case: EvalCaseCreate,
        form_id: str,
        form_version: str,
        form_kind: str,
    ) -> None:
        if not case.ground_truths:
            raise ValueError(
                f"Evaluation case {case.claim_number} needs at least one ground truth."
            )
        kinds = {truth.reference_kind for truth in case.ground_truths}
        if not kinds & {"R1", "R2"}:
            raise ValueError(f"Evaluation case {case.claim_number} needs an R1 or R2 ground truth.")
        for truth in case.ground_truths:
            if truth.result.form_id != form_id or truth.result.form_version != form_version:
                raise ValueError(
                    f"Ground truth for claim {case.claim_number} must use {form_id}@{form_version}."
                )
            if truth.result.form_kind != form_kind:
                raise ValueError(
                    f"Ground truth for claim {case.claim_number} must use {form_kind} form kind."
                )


@dataclass(slots=True)
class EvaluationRunService:
    settings: Settings = field(default_factory=get_settings)

    async def run(self, run_id: str) -> None:
        try:
            async with AsyncSessionLocal() as session:
                repository = EvaluationRepository(session)
                run = await repository.mark_run_running(run_id)
                await self._maybe_start_mlflow(repository, run)
                items = await repository.queued_items_for_run(run_id)

            semaphore = asyncio.Semaphore(max(1, run.concurrency))

            async def run_item(item: EvalRunItemRecord) -> None:
                async with semaphore:
                    await self._run_item(run_id, item.id)

            await asyncio.gather(*(run_item(item) for item in items))

            async with AsyncSessionLocal() as session:
                repository = EvaluationRepository(session)
                final_run = await repository.refresh_run_counts(run_id)
                await self._maybe_finish_mlflow(final_run)
        except Exception as exc:
            async with AsyncSessionLocal() as session:
                await EvaluationRepository(session).mark_run_failed(run_id, str(exc))

    async def _run_item(self, run_id: str, item_id: str) -> None:
        async with AsyncSessionLocal() as session:
            repository = EvaluationRepository(session)
            run = await repository.run_snapshot(run_id)
            if run.status != "running":
                return
            item = await repository.mark_item_running(item_id)
            case = await repository.case_for_item(item.id)

        try:
            async with AsyncSessionLocal() as session:
                repository = EvaluationRepository(session)
                run = await repository.run_snapshot(run_id)
                dataset = await repository._get_dataset_orm(run.dataset_id)
                request = ReviewGenerateRequest(
                    prompt=case.instructions,
                    claim_number=case.claim_number,
                    effective_date=case.effective_date or "",
                    instructions=case.instructions,
                    form_id=dataset.form_id,
                    form_version=dataset.form_version,
                    prompt_ref=PromptReference.model_validate(run.input_json["prompt_ref"])
                    if (run.input_json or {}).get("prompt_ref")
                    else None,
                    eval_run_id=run.id,
                    eval_run_name=run.name,
                    eval_dataset_id=dataset.id,
                    eval_result_role="model",
                    eval_config_version=run.config_version,
                )
                review = await AuditGenerationService(session, self.settings).generate_new_review(
                    request,
                    source="eval",
                )
                if review.status != "completed" or not review.original:
                    raise RuntimeError(review.error_message or "Audit generation did not complete.")
                truths = await repository.ground_truths_for_case(case.id)
                comparisons = []
                for truth in truths:
                    reference_result = parse_audit_result(truth.payload_json)
                    comparisons.append(
                        (
                            truth,
                            reference_result,
                            compare_audit_results(
                                generated=review.original,
                                reference=reference_result,
                            ),
                        )
                    )
                await repository.complete_item(
                    item_id,
                    generated_review_id=review.id,
                    generated_result=review.original,
                    comparisons=comparisons,
                )
        except Exception as exc:
            async with AsyncSessionLocal() as session:
                await EvaluationRepository(session).fail_item(item_id, str(exc))

    async def _maybe_start_mlflow(
        self,
        repository: EvaluationRepository,
        run: EvalRunRecord,
    ) -> None:
        if not run.enable_mlflow:
            return
        try:
            import mlflow

            active_run = mlflow.start_run(run_name=run.name)
            orm = await repository.run_snapshot(run.id)
            orm.mlflow_run_id = active_run.info.run_id
            repository.session.add(orm)
            await repository.session.commit()
            mlflow.log_params(
                {
                    "dataset_id": run.dataset_id,
                    "dataset_name": run.dataset_name,
                    "model_name": run.model_name,
                    "reference_policy": run.reference_policy,
                }
            )
        except Exception:
            return

    async def _maybe_finish_mlflow(self, run: EvalRunRecord) -> None:
        if not run.enable_mlflow:
            return
        try:
            import mlflow

            metrics = {
                "completed_count": run.completed_count,
                "failed_count": run.failed_count,
                "progress_percent": run.progress_percent,
            }
            if run.primary_score is not None:
                metrics["primary_score"] = run.primary_score
            metrics.update(
                {
                    metric_name: metric_value
                    for metric_name, metric_value in run.metrics.items()
                    if isinstance(metric_value, (int, float))
                }
            )
            mlflow.log_metrics(metrics)
            mlflow.end_run(status="FINISHED" if run.status == "completed" else "FAILED")
        except Exception:
            return


async def run_evaluation_job(run_id: str, settings: Settings | None = None) -> None:
    await EvaluationRunService(settings or get_settings()).run(run_id)
