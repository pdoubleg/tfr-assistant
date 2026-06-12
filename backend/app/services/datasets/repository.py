from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import Settings, get_settings
from app.db.models import (
    AuditResultVersionORM,
    AuditReviewORM,
    DatasetCandidateORM,
    DatasetPopulationORM,
    EvalCaseORM,
    EvalDatasetORM,
    EvalGroundTruthORM,
    FeedbackORM,
)
from app.models.audit import (
    AuditResult,
    financial_totals,
    parse_audit_result,
)
from app.schemas.datasets import (
    CanonicalDatasetCandidate,
    DatasetAddCandidatesResponse,
    DatasetAppDbAddRequest,
    DatasetAppDbBrowseRequest,
    DatasetCandidateRecord,
    DatasetCandidateReferenceUpdate,
    DatasetCandidateUpdate,
    DatasetCloneRequest,
    DatasetClusterRequest,
    DatasetClusterResult,
    DatasetMaterializeResponse,
    DatasetPopulationCreate,
    DatasetPopulationDetail,
    DatasetPopulationRecord,
    DatasetPopulationUpdate,
    DatasetPublishRequest,
    DatasetReference,
    DatasetSampleRequest,
    DatasetSampleResult,
    DatasetSourceAddRequest,
    DatasetSourceBrowseRequest,
    DatasetSourceFetchRequest,
    DatasetSourceRecord,
    DatasetSourceRowRecord,
    PublishedDatasetRow,
)
from app.schemas.evaluations import EvalCaseCreate, EvalDatasetCreate
from app.services.catalog import FormCatalog
from app.services.datasets.clustering import (
    _candidate_vectors,
    _cluster_vectors,
    _sample_candidates,
    _sample_reason,
)
from app.services.datasets.sources import fetch_source_candidates, list_for_form
from app.services.evaluation_service import EvaluationRepository
from app.services.optimization.metrics import driver_count, issue_count
from app.services.review_repository import ReviewRepository


def _now() -> datetime:
    return datetime.now(UTC)


def _json_hash(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode(
        "utf-8"
    )
    return hashlib.sha256(encoded).hexdigest()


def _string(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _payload_for(result: AuditResult) -> dict[str, Any]:
    return result.model_dump(mode="json")


def _candidate_metrics(result: AuditResult) -> dict[str, Any]:
    totals = financial_totals(result)
    return {
        "outcome": result.overall_outcome,
        "issue_count": issue_count(result),
        "driver_count": driver_count(result),
        "question_count": len(result.questions),
        "total_amount_reviewed_dollars": float(totals["total_amount_reviewed_dollars"]),
        "total_overwrite_dollars": float(totals["total_overwrite_dollars"]),
        "total_underwrite_dollars": float(totals["total_underwrite_dollars"]),
        "overwrite_percent": float(totals["overwrite_percent"]),
        "underwrite_percent": float(totals["underwrite_percent"]),
    }


def _feedback_metrics(metadata: dict[str, Any] | None) -> dict[str, Any]:
    feedback = (metadata or {}).get("feedback")
    if not isinstance(feedback, dict):
        return {}
    metrics: dict[str, Any] = {}
    for source_key, metric_key in (
        ("count", "feedback_count"),
        ("average_score", "feedback_average_score"),
        ("min_score", "feedback_min_score"),
        ("latest_score", "feedback_latest_score"),
    ):
        value = feedback.get(source_key)
        if isinstance(value, int | float):
            metrics[metric_key] = value
    return metrics


def _preferred_reference(references: list[dict[str, Any]]) -> DatasetReference:
    parsed = [DatasetReference.model_validate(reference) for reference in references]
    return next((reference for reference in parsed if reference.reference_kind == "R2"), parsed[0])


def _dedupe_key_for(
    source_key: str,
    source_record_id: str,
    references: list[DatasetReference],
) -> str:
    return _json_hash(
        {
            "source_key": source_key,
            "source_record_id": source_record_id,
            "references": [reference.result.model_dump(mode="json") for reference in references],
        }
    )


def _reference_payload(reference: DatasetReference) -> dict[str, Any]:
    return {
        "reference_kind": reference.reference_kind,
        "result": _payload_for(reference.result),
        "reviewer": reference.reviewer,
        "source_metadata": reference.source_metadata,
    }


def _materialized_source_for(source_key: str) -> str:
    source = f"dataset:{source_key}"
    return source if len(source) <= 32 else source[:32]


class DatasetRepository:
    def __init__(self, session: AsyncSession, settings: Settings | None = None) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.catalog = FormCatalog(self.settings.form_catalog_dir)

    def list_sources(self, form_id: str, form_version: str) -> list[DatasetSourceRecord]:
        return list_for_form(self.catalog, form_id, form_version)

    async def create_population(self, request: DatasetPopulationCreate) -> DatasetPopulationRecord:
        form = self.catalog.get_form(request.form_id, request.form_version)
        population = DatasetPopulationORM(
            id=str(uuid4()),
            name=request.name.strip(),
            description=request.description.strip(),
            form_id=form.id,
            form_version=form.version,
            form_kind=form.form_kind,
            status="draft",
        )
        self.session.add(population)
        await self.session.commit()
        await self.session.refresh(population)
        return await self._population_to_schema(population)

    async def update_population(
        self,
        population_id: str,
        request: DatasetPopulationUpdate,
    ) -> DatasetPopulationRecord:
        population = await self._get_population_orm(population_id)
        self._require_draft_population(population)
        if request.name is not None:
            population.name = request.name.strip()
        if request.description is not None:
            population.description = request.description.strip()
        population.updated_at = _now()
        await self.session.commit()
        await self.session.refresh(population)
        return await self._population_to_schema(population)

    async def list_populations(
        self,
        form_id: str | None = None,
        form_version: str | None = None,
    ) -> list[DatasetPopulationRecord]:
        statement = select(DatasetPopulationORM).order_by(DatasetPopulationORM.updated_at.desc())
        if form_id:
            statement = statement.where(DatasetPopulationORM.form_id == form_id)
        if form_version:
            statement = statement.where(DatasetPopulationORM.form_version == form_version)
        records = (await self.session.scalars(statement)).all()
        return [await self._population_to_schema(record) for record in records]

    async def get_population(self, population_id: str) -> DatasetPopulationDetail:
        population = await self._get_population_orm(population_id)
        base = await self._population_to_schema(population)
        candidates = await self._candidate_rows(population.id)
        return DatasetPopulationDetail(
            **base.model_dump(),
            candidates=[self._candidate_to_schema(candidate) for candidate in candidates],
        )

    async def fetch_source(
        self,
        population_id: str,
        request: DatasetSourceFetchRequest,
    ) -> DatasetAddCandidatesResponse:
        population = await self._get_population_orm(population_id)
        self._require_draft_population(population)
        candidates = self._fetch_source_candidates(
            request.source_id,
            form_id=population.form_id,
            form_version=population.form_version,
            params=request.params,
        )
        population.source_config_json = {
            "last_source_id": request.source_id,
            "last_params": request.params,
            "last_fetched_at": _now().isoformat(),
        }
        return await self._add_canonical_candidates(population, candidates)

    async def browse_source(
        self,
        form_id: str,
        form_version: str,
        request: DatasetSourceBrowseRequest,
    ) -> list[DatasetSourceRowRecord]:
        candidates = self._fetch_source_candidates(
            request.source_id,
            form_id=form_id,
            form_version=form_version,
            params=request.params,
        )
        return [
            self._candidate_to_source_row(candidate) for candidate in candidates[: request.limit]
        ]

    async def add_source_candidates(
        self,
        population_id: str,
        request: DatasetSourceAddRequest,
    ) -> DatasetAddCandidatesResponse:
        population = await self._get_population_orm(population_id)
        self._require_draft_population(population)
        candidates = self._fetch_source_candidates(
            request.source_id,
            form_id=population.form_id,
            form_version=population.form_version,
            params=request.params,
        )[: request.limit]
        if not request.add_all_filtered:
            selected_ids = set(request.source_record_ids)
            if not selected_ids:
                raise ValueError("Select at least one source row before adding candidates.")
            candidates = [
                candidate for candidate in candidates if candidate.source_record_id in selected_ids
            ]
        population.source_config_json = {
            "last_source_id": request.source_id,
            "last_params": request.params,
            "last_added_at": _now().isoformat(),
            "last_selected_count": len(candidates),
            "last_add_all_filtered": request.add_all_filtered,
        }
        return await self._add_canonical_candidates(population, candidates)

    async def materialize_source_reviews(
        self,
        form_id: str,
        form_version: str,
        request: DatasetSourceAddRequest,
    ) -> DatasetMaterializeResponse:
        self.catalog.get_form(form_id, form_version)
        candidates = self._fetch_source_candidates(
            request.source_id,
            form_id=form_id,
            form_version=form_version,
            params=request.params,
        )[: request.limit]
        if not request.add_all_filtered:
            selected_ids = set(request.source_record_ids)
            if not selected_ids:
                raise ValueError("Select at least one source row before importing reviews.")
            candidates = [
                candidate for candidate in candidates if candidate.source_record_id in selected_ids
            ]

        created_ids: list[str] = []
        skipped_ids: list[str] = []
        repository = ReviewRepository(self.session)
        for candidate in candidates:
            if await self._materialized_review_exists(candidate):
                skipped_ids.append(candidate.source_record_id)
                continue
            reference = next(
                (item for item in candidate.references if item.reference_kind == "R2"),
                candidate.references[0],
            )
            input_json = {
                **candidate.input,
                "claim_number": candidate.claim_number,
                "effective_date": candidate.effective_date,
                "instructions": candidate.instructions,
                "dataset_materialized": True,
                "dataset_source_key": candidate.source_key,
                "dataset_source_kind": candidate.source_kind,
                "dataset_source_label": candidate.source_label,
                "dataset_source_record_id": candidate.source_record_id,
                "dataset_source_metadata": candidate.metadata or {},
                "dataset_reference_kind": reference.reference_kind,
                "dataset_reference_source_metadata": reference.source_metadata or {},
            }
            review = await repository.create_from_agent_output(
                reference.result,
                source=_materialized_source_for(candidate.source_key),
                input_json=input_json,
            )
            created_ids.append(review.id)

        return DatasetMaterializeResponse(
            created_count=len(created_ids),
            skipped_count=len(skipped_ids),
            review_ids=created_ids,
            skipped_source_record_ids=skipped_ids,
        )

    async def browse_app_db_source(
        self,
        form_id: str,
        form_version: str,
        request: DatasetAppDbBrowseRequest,
    ) -> list[DatasetSourceRowRecord]:
        reviews = await self._app_db_review_rows(
            form_id=form_id,
            form_version=form_version,
            search=request.search,
            source=request.source,
            outcome=request.outcome,
            result_version=request.result_version,
            limit=request.limit,
            review_ids=None,
        )
        feedback_summaries = await self._feedback_summaries(
            [review.id for review in reviews],
            enabled=request.include_feedback or request.feedback_filter != "all",
        )
        reviews = self._filter_reviews_by_feedback(
            reviews,
            feedback_summaries,
            request.feedback_filter,
        )
        return [
            self._review_to_source_row(
                review,
                request.result_version,
                feedback_summary=feedback_summaries.get(review.id)
                if request.include_feedback
                else None,
            )
            for review in reviews
        ]

    async def add_app_db_source(
        self,
        population_id: str,
        request: DatasetAppDbAddRequest,
    ) -> DatasetAddCandidatesResponse:
        population = await self._get_population_orm(population_id)
        self._require_draft_population(population)
        review_ids = request.review_ids if not request.add_all_filtered else None
        reviews = await self._app_db_review_rows(
            form_id=population.form_id,
            form_version=population.form_version,
            search=request.search,
            source=request.source,
            outcome=request.outcome,
            result_version=request.result_version,
            limit=request.limit,
            review_ids=review_ids,
        )
        feedback_summaries = await self._feedback_summaries(
            [review.id for review in reviews],
            enabled=request.include_feedback or request.feedback_filter != "all",
        )
        reviews = self._filter_reviews_by_feedback(
            reviews,
            feedback_summaries,
            request.feedback_filter,
        )
        candidates = [
            self._review_to_candidate(
                review,
                request.result_version,
                feedback_summary=feedback_summaries.get(review.id)
                if request.include_feedback
                else None,
            )
            for review in reviews
            if self._version_for_review(review, request.result_version) is not None
        ]
        return await self._add_canonical_candidates(population, candidates)

    async def update_candidate(
        self,
        candidate_id: str,
        request: DatasetCandidateUpdate,
    ) -> DatasetCandidateRecord:
        candidate = await self._get_candidate_orm(candidate_id)
        population = await self._get_population_orm(candidate.population_id)
        self._require_draft_population(population)
        if request.included is not None:
            candidate.included = request.included
        if request.tags is not None:
            candidate.tags_json = request.tags
        if request.sample_reason is not None:
            candidate.sample_reason = request.sample_reason
        candidate.updated_at = _now()
        await self.session.commit()
        await self.session.refresh(candidate)
        return self._candidate_to_schema(candidate)

    async def update_candidate_reference(
        self,
        candidate_id: str,
        reference_kind: Literal["R1", "R2"],
        request: DatasetCandidateReferenceUpdate,
    ) -> DatasetCandidateRecord:
        candidate = await self._get_candidate_orm(candidate_id)
        population = await self._get_population_orm(candidate.population_id)
        self._require_draft_population(population)
        update_reference = DatasetReference(
            reference_kind=reference_kind,
            result=request.result,
            reviewer=request.reviewer,
            source_metadata=request.source_metadata,
        )
        self._validate_candidate(
            CanonicalDatasetCandidate(
                source_key=candidate.source_key,
                source_kind=candidate.source_kind,
                source_label=candidate.source_label,
                source_record_id=candidate.source_record_id,
                claim_number=candidate.claim_number,
                effective_date=candidate.effective_date,
                instructions=candidate.instructions,
                input=candidate.input_json or {},
                references=[update_reference],
                metadata=candidate.metadata_json,
                tags=candidate.tags_json or [],
            ),
            population,
        )

        references = [
            DatasetReference.model_validate(reference)
            for reference in candidate.references_json or []
        ]
        replaced = False
        for index, reference in enumerate(references):
            if reference.reference_kind == reference_kind:
                references[index] = update_reference
                replaced = True
                break
        if not replaced:
            references.append(update_reference)
        references = sorted(references, key=lambda item: item.reference_kind)

        next_dedupe_key = _dedupe_key_for(
            candidate.source_key,
            candidate.source_record_id,
            references,
        )
        existing = await self.session.scalar(
            select(DatasetCandidateORM).where(
                DatasetCandidateORM.population_id == population.id,
                DatasetCandidateORM.dedupe_key == next_dedupe_key,
                DatasetCandidateORM.id != candidate.id,
            )
        )
        if existing:
            raise ValueError("Edited candidate would duplicate another candidate in this draft.")

        edited_at = _now().isoformat()
        metadata = dict(candidate.metadata_json or {})
        curation = dict(metadata.get("curation") or {})
        edited_kinds = set(curation.get("edited_reference_kinds") or [])
        edited_kinds.add(reference_kind)
        edits = list(curation.get("reference_edits") or [])
        edits.append(
            {
                "reference_kind": reference_kind,
                "edited_at": edited_at,
                "reviewer": request.reviewer,
            }
        )
        curation.update(
            {
                "edited": True,
                "last_edited_at": edited_at,
                "edited_reference_kinds": sorted(edited_kinds),
                "reference_edits": edits,
            }
        )
        metadata["curation"] = curation
        metadata["curated_edited"] = True

        preferred = next(
            (reference.result for reference in references if reference.reference_kind == "R2"),
            references[0].result,
        )
        candidate.references_json = [_reference_payload(reference) for reference in references]
        candidate.dedupe_key = next_dedupe_key
        candidate.metrics_json = {
            **_candidate_metrics(preferred),
            **_feedback_metrics(metadata),
        }
        candidate.metadata_json = metadata
        candidate.sample_reason = candidate.sample_reason or "Edited in dataset draft."
        candidate.updated_at = _now()
        await self._mark_analysis_stale(
            population,
            reason=f"reference_{reference_kind.lower()}_edited",
            candidate_id=candidate.id,
        )
        await self.session.commit()
        await self.session.refresh(candidate)
        return self._candidate_to_schema(candidate)

    async def cluster_population(
        self,
        population_id: str,
        request: DatasetClusterRequest,
    ) -> DatasetClusterResult:
        population = await self._get_population_orm(population_id)
        self._require_draft_population(population)
        candidates = [
            candidate
            for candidate in await self._candidate_rows(population.id)
            if candidate.included
        ]
        if len(candidates) < 2:
            raise ValueError("At least two included candidates are required for clustering.")

        vectors, backend = _candidate_vectors(candidates, self.settings, request)
        selected_k, labels, distances, silhouette = _cluster_vectors(
            vectors,
            min_k=request.min_clusters,
            max_k=request.max_clusters,
            seed=request.seed,
        )
        cluster_counts: dict[str, int] = {}
        for candidate, label, distance in zip(candidates, labels, distances, strict=True):
            cluster_counts[str(label)] = cluster_counts.get(str(label), 0) + 1
            candidate.cluster_id = label
            candidate.cluster_distance = distance
            candidate.cluster_score = silhouette
            candidate.cluster_metadata_json = {
                "feature_backend": backend,
                "selected_k": selected_k,
                "silhouette_score": silhouette,
            }
            candidate.updated_at = _now()
            self.session.add(candidate)
        population.cluster_config_json = {
            **request.model_dump(mode="json"),
            "feature_backend": backend,
            "selected_k": selected_k,
            "silhouette_score": silhouette,
            "cluster_counts": cluster_counts,
            "clustered_at": _now().isoformat(),
        }
        population.updated_at = _now()
        await self.session.commit()
        await self.session.refresh(population)
        return DatasetClusterResult(
            population=await self._population_to_schema(population),
            feature_backend=backend,
            selected_k=selected_k,
            clustered_count=len(candidates),
            silhouette_score=silhouette,
            cluster_counts=cluster_counts,
        )

    async def sample_population(
        self,
        population_id: str,
        request: DatasetSampleRequest,
    ) -> DatasetSampleResult:
        population = await self._get_population_orm(population_id)
        self._require_draft_population(population)
        candidates = await self._candidate_rows(population.id)
        selected_ids = _sample_candidates(candidates, request)
        for candidate in candidates:
            candidate.included = candidate.id in selected_ids
            candidate.sample_reason = _sample_reason(candidate, request, candidate.included)
            candidate.updated_at = _now()
            self.session.add(candidate)
        population.sample_config_json = {
            **request.model_dump(mode="json"),
            "selected_count": len(selected_ids),
            "sampled_at": _now().isoformat(),
        }
        population.updated_at = _now()
        await self.session.commit()
        await self.session.refresh(population)
        return DatasetSampleResult(
            population=await self._population_to_schema(population),
            selected_count=len(selected_ids),
            mode=request.mode,
            sample_config=population.sample_config_json or {},
        )

    async def publish_population(
        self,
        population_id: str,
        request: DatasetPublishRequest,
    ):
        population = await self._get_population_orm(population_id)
        self._require_draft_population(population)
        candidates = await self._candidate_rows(population.id)
        selected = [
            candidate for candidate in candidates if candidate.included or not request.include_only
        ]
        if not selected:
            raise ValueError("Select at least one candidate before publishing a dataset.")
        cases = []
        for candidate in selected:
            references = [
                DatasetReference.model_validate(item) for item in candidate.references_json
            ]
            if not references:
                raise ValueError(f"Candidate {candidate.claim_number} has no references.")
            cases.append(
                EvalCaseCreate(
                    claim_number=candidate.claim_number,
                    effective_date=candidate.effective_date,
                    instructions=candidate.instructions,
                    input=candidate.input_json or {},
                    metadata={
                        "dataset_candidate_id": candidate.id,
                        "source_kind": candidate.source_kind,
                        "source_key": candidate.source_key,
                        "source_label": candidate.source_label,
                        "source_record_id": candidate.source_record_id,
                        "dedupe_key": candidate.dedupe_key,
                        "candidate_metadata": candidate.metadata_json or {},
                        "candidate_metrics": candidate.metrics_json or {},
                        "tags": candidate.tags_json or [],
                        "cluster_id": candidate.cluster_id,
                        "cluster_distance": candidate.cluster_distance,
                        "cluster_score": candidate.cluster_score,
                        "cluster_metadata": candidate.cluster_metadata_json or {},
                        "sample_reason": candidate.sample_reason,
                    },
                    ground_truths=[
                        {
                            "reference_kind": reference.reference_kind,
                            "result": reference.result,
                            "reviewer": reference.reviewer,
                            "source_metadata": reference.source_metadata,
                        }
                        for reference in references
                    ],
                )
            )
        dataset = await EvaluationRepository(self.session).create_dataset(
            EvalDatasetCreate(
                name=request.name,
                description=request.description,
                form_id=population.form_id,
                form_version=population.form_version,
                form_kind=population.form_kind,  # type: ignore[arg-type]
                source_kind="curated",
                source_metadata={
                    "population_id": population.id,
                    "population_name": population.name,
                    "candidate_count": len(candidates),
                    "included_count": len(selected),
                    "cluster_config": population.cluster_config_json,
                    "sample_config": population.sample_config_json,
                },
                cases=cases,
            )
        )
        population.status = "published"
        population.published_dataset_id = dataset.id
        population.updated_at = _now()
        await self.session.commit()
        return dataset

    async def list_published_datasets(self):
        return await EvaluationRepository(self.session).list_datasets()

    async def get_published_dataset(self, dataset_id: str):
        return await EvaluationRepository(self.session).get_dataset(dataset_id)

    async def clone_published_dataset(
        self,
        dataset_id: str,
        request: DatasetCloneRequest,
    ) -> DatasetPopulationDetail:
        dataset = await self.session.get(EvalDatasetORM, dataset_id)
        if not dataset:
            raise KeyError(f"Unknown dataset: {dataset_id}")
        cases = (
            await self.session.scalars(
                select(EvalCaseORM)
                .options(selectinload(EvalCaseORM.ground_truths))
                .where(EvalCaseORM.dataset_id == dataset_id)
                .order_by(EvalCaseORM.created_at.asc())
            )
        ).all()
        population = DatasetPopulationORM(
            id=str(uuid4()),
            name=(request.name or f"{dataset.name} Draft Copy").strip()[:120],
            description=(
                request.description
                if request.description is not None
                else f"Cloned from published dataset {dataset.name}."
            ).strip(),
            form_id=dataset.form_id,
            form_version=dataset.form_version,
            form_kind=dataset.form_kind,
            status="draft",
            source_config_json={
                "cloned_from_dataset_id": dataset.id,
                "cloned_from_dataset_name": dataset.name,
                "cloned_at": _now().isoformat(),
            },
            cluster_config_json=(dataset.source_metadata_json or {}).get("cluster_config"),
            sample_config_json=(dataset.source_metadata_json or {}).get("sample_config"),
        )
        self.session.add(population)
        await self.session.flush()

        for case in cases:
            references = [
                DatasetReference(
                    reference_kind=truth.reference_kind,  # type: ignore[arg-type]
                    result=parse_audit_result(truth.payload_json),
                    reviewer=truth.reviewer,
                    source_metadata=truth.source_metadata_json,
                )
                for truth in sorted(
                    case.ground_truths,
                    key=lambda truth: truth.reference_kind,
                )
            ]
            if not references:
                continue
            case_metadata = case.metadata_json or {}
            source_key = _string(case_metadata.get("source_key")) or dataset.id
            source_record_id = _string(case_metadata.get("source_record_id")) or case.id
            candidate_metadata = (
                dict(case_metadata.get("candidate_metadata"))
                if isinstance(case_metadata.get("candidate_metadata"), dict)
                else {}
            )
            candidate_metadata.update(
                {
                    "cloned_from_dataset_id": dataset.id,
                    "cloned_from_dataset_name": dataset.name,
                    "cloned_from_case_id": case.id,
                    "original_case_metadata": case_metadata,
                }
            )
            tags = [tag for tag in case_metadata.get("tags", []) if isinstance(tag, str)]
            if "cloned" not in tags:
                tags.append("cloned")
            preferred = next(
                (reference.result for reference in references if reference.reference_kind == "R2"),
                references[0].result,
            )
            candidate = DatasetCandidateORM(
                id=str(uuid4()),
                population_id=population.id,
                source_kind=_string(case_metadata.get("source_kind")) or "published_dataset",
                source_key=source_key,
                source_label=_string(case_metadata.get("source_label")) or dataset.name,
                source_record_id=source_record_id,
                dedupe_key=_dedupe_key_for(source_key, source_record_id, references),
                claim_number=case.claim_number,
                effective_date=case.effective_date,
                instructions=case.instructions,
                input_json=case.input_json or {},
                references_json=[_reference_payload(reference) for reference in references],
                metadata_json=candidate_metadata,
                tags_json=tags,
                metrics_json=_candidate_metrics(preferred),
                included=True,
                cluster_id=case_metadata.get("cluster_id")
                if isinstance(case_metadata.get("cluster_id"), int)
                else None,
                cluster_distance=case_metadata.get("cluster_distance")
                if isinstance(case_metadata.get("cluster_distance"), (int, float))
                else None,
                cluster_score=case_metadata.get("cluster_score")
                if isinstance(case_metadata.get("cluster_score"), (int, float))
                else None,
                cluster_metadata_json=case_metadata.get("cluster_metadata")
                if isinstance(case_metadata.get("cluster_metadata"), dict)
                else None,
                sample_reason=_string(case_metadata.get("sample_reason"))
                or "Cloned from published dataset.",
            )
            self.session.add(candidate)

        population.updated_at = _now()
        await self.session.commit()
        return await self.get_population(population.id)

    async def list_published_rows(self, dataset_id: str) -> list[PublishedDatasetRow]:
        dataset = await self.session.get(EvalDatasetORM, dataset_id)
        if not dataset:
            raise KeyError(f"Unknown dataset: {dataset_id}")
        rows = (
            await self.session.execute(
                select(EvalCaseORM, EvalGroundTruthORM)
                .join(EvalGroundTruthORM, EvalGroundTruthORM.case_id == EvalCaseORM.id)
                .where(EvalCaseORM.dataset_id == dataset_id)
                .order_by(EvalCaseORM.created_at.asc(), EvalGroundTruthORM.reference_kind.asc())
            )
        ).all()
        output: list[PublishedDatasetRow] = []
        for case, truth in rows:
            metadata = case.metadata_json or {}
            result = parse_audit_result(truth.payload_json)
            output.append(
                PublishedDatasetRow(
                    dataset_id=dataset.id,
                    dataset_name=dataset.name,
                    case_id=case.id,
                    ground_truth_id=truth.id,
                    reference_kind=truth.reference_kind,  # type: ignore[arg-type]
                    form_id=dataset.form_id,
                    form_version=dataset.form_version,
                    form_kind=dataset.form_kind,  # type: ignore[arg-type]
                    claim_number=case.claim_number,
                    effective_date=case.effective_date,
                    source_kind=_string(metadata.get("source_kind")),
                    source_key=_string(metadata.get("source_key")),
                    source_label=_string(metadata.get("source_label")),
                    source_record_id=_string(metadata.get("source_record_id")),
                    cluster_id=metadata.get("cluster_id")
                    if isinstance(metadata.get("cluster_id"), int)
                    else None,
                    sample_reason=_string(metadata.get("sample_reason")),
                    metadata=metadata,
                    result=result,
                    created_at=case.created_at,
                    updated_at=case.updated_at,
                )
            )
        return output

    def _fetch_source_candidates(
        self,
        source_id: str,
        *,
        form_id: str,
        form_version: str,
        params: dict[str, Any] | None,
    ) -> list[CanonicalDatasetCandidate]:
        form = self.catalog.get_form(form_id, form_version)
        candidates = fetch_source_candidates(
            source_id,
            catalog=self.catalog,
            form_id=form_id,
            form_version=form_version,
            params=params,
        )
        population_shape = DatasetPopulationORM(
            id="validation-only",
            name="validation-only",
            description="",
            form_id=form_id,
            form_version=form_version,
            form_kind=form.form_kind,
            status="draft",
        )
        for candidate in candidates:
            self._validate_candidate(candidate, population_shape)
        return candidates

    def _candidate_to_source_row(
        self,
        candidate: CanonicalDatasetCandidate,
    ) -> DatasetSourceRowRecord:
        preferred = next(
            (
                reference.result
                for reference in candidate.references
                if reference.reference_kind == "R2"
            ),
            candidate.references[0].result,
        )
        metrics = _candidate_metrics(preferred)
        return DatasetSourceRowRecord(
            source_record_id=candidate.source_record_id,
            review_id=candidate.source_record_id,
            source_id=candidate.source_key,
            source_kind=candidate.source_kind,
            source_label=candidate.source_label,
            source=candidate.source_label or candidate.source_key,
            claim_number=candidate.claim_number,
            effective_date=candidate.effective_date,
            title=preferred.title,
            outcome=preferred.overall_outcome,
            issue_count=int(metrics["issue_count"]),
            driver_count=int(metrics["driver_count"]),
            total_amount_reviewed_dollars=metrics["total_amount_reviewed_dollars"],
            total_overwrite_dollars=metrics["total_overwrite_dollars"],
            total_underwrite_dollars=metrics["total_underwrite_dollars"],
        )

    async def _add_canonical_candidates(
        self,
        population: DatasetPopulationORM,
        candidates: list[CanonicalDatasetCandidate],
    ) -> DatasetAddCandidatesResponse:
        added_ids: list[str] = []
        skipped = 0
        for candidate in candidates:
            self._validate_candidate(candidate, population)
            preferred = next(
                (
                    reference.result
                    for reference in candidate.references
                    if reference.reference_kind == "R2"
                ),
                candidate.references[0].result,
            )
            dedupe_key = _dedupe_key_for(
                candidate.source_key,
                candidate.source_record_id,
                candidate.references,
            )
            existing = await self.session.scalar(
                select(DatasetCandidateORM).where(
                    DatasetCandidateORM.population_id == population.id,
                    DatasetCandidateORM.dedupe_key == dedupe_key,
                )
            )
            if existing:
                skipped += 1
                continue
            metrics = {
                **_candidate_metrics(preferred),
                **_feedback_metrics(candidate.metadata),
            }
            record = DatasetCandidateORM(
                id=str(uuid4()),
                population_id=population.id,
                source_kind=candidate.source_kind,
                source_key=candidate.source_key,
                source_label=candidate.source_label,
                source_record_id=candidate.source_record_id,
                dedupe_key=dedupe_key,
                claim_number=candidate.claim_number.strip(),
                effective_date=candidate.effective_date,
                instructions=candidate.instructions,
                input_json=candidate.input,
                references_json=[
                    _reference_payload(reference) for reference in candidate.references
                ],
                metadata_json=candidate.metadata,
                tags_json=candidate.tags,
                metrics_json=metrics,
                included=True,
                sample_reason="Added to candidate pool.",
            )
            self.session.add(record)
            added_ids.append(record.id)
        population.updated_at = _now()
        self.session.add(population)
        await self.session.commit()
        await self.session.refresh(population)
        return DatasetAddCandidatesResponse(
            population=await self._population_to_schema(population),
            added_count=len(added_ids),
            skipped_count=skipped,
            candidate_ids=added_ids,
        )

    def _validate_candidate(
        self,
        candidate: CanonicalDatasetCandidate,
        population: DatasetPopulationORM,
    ) -> None:
        for reference in candidate.references:
            result = reference.result
            if (
                result.form_id != population.form_id
                or result.form_version != population.form_version
            ):
                raise ValueError(
                    f"Candidate {candidate.claim_number} references "
                    f"{result.form_id}@{result.form_version}, expected "
                    f"{population.form_id}@{population.form_version}."
                )
            if result.form_kind != population.form_kind:
                raise ValueError(
                    f"Candidate {candidate.claim_number} uses form kind {result.form_kind}, "
                    f"expected {population.form_kind}."
                )

    def _require_draft_population(self, population: DatasetPopulationORM) -> None:
        if population.status != "draft":
            raise ValueError(
                "Published dataset populations are immutable. Clone to a new draft before editing."
            )

    async def _mark_analysis_stale(
        self,
        population: DatasetPopulationORM,
        *,
        reason: str,
        candidate_id: str,
    ) -> None:
        marked_at = _now().isoformat()
        candidates = await self._candidate_rows(population.id)
        for candidate in candidates:
            candidate.cluster_id = None
            candidate.cluster_distance = None
            candidate.cluster_score = None
            candidate.cluster_metadata_json = None
            candidate.updated_at = _now()
            self.session.add(candidate)

        cluster_config = dict(population.cluster_config_json or {})
        if cluster_config:
            cluster_config.update(
                {
                    "stale": True,
                    "stale_reason": reason,
                    "stale_candidate_id": candidate_id,
                    "stale_at": marked_at,
                }
            )
            population.cluster_config_json = cluster_config

        sample_config = dict(population.sample_config_json or {})
        if sample_config:
            sample_config.update(
                {
                    "stale": True,
                    "stale_reason": reason,
                    "stale_candidate_id": candidate_id,
                    "stale_at": marked_at,
                }
            )
            population.sample_config_json = sample_config

        population.updated_at = _now()
        self.session.add(population)

    async def _materialized_review_exists(self, candidate: CanonicalDatasetCandidate) -> bool:
        source = _materialized_source_for(candidate.source_key)
        records = (
            await self.session.scalars(
                select(AuditReviewORM).where(
                    AuditReviewORM.form_id == candidate.references[0].result.form_id,
                    AuditReviewORM.form_version == candidate.references[0].result.form_version,
                    AuditReviewORM.status == "completed",
                    AuditReviewORM.source == source,
                )
            )
        ).all()
        for record in records:
            input_json = record.input_json or {}
            if (
                input_json.get("dataset_materialized") is True
                and input_json.get("dataset_source_key") == candidate.source_key
                and input_json.get("dataset_source_record_id") == candidate.source_record_id
            ):
                return True
        return False

    async def _app_db_review_rows(
        self,
        *,
        form_id: str,
        form_version: str,
        search: str,
        source: str,
        outcome: str,
        result_version: str,
        limit: int,
        review_ids: list[str] | None,
    ) -> list[AuditReviewORM]:
        statement = (
            select(AuditReviewORM)
            .options(selectinload(AuditReviewORM.versions))
            .where(
                AuditReviewORM.form_id == form_id,
                AuditReviewORM.form_version == form_version,
                AuditReviewORM.status == "completed",
            )
            .order_by(AuditReviewORM.updated_at.desc())
            .limit(limit)
        )
        if source != "all":
            statement = statement.where(AuditReviewORM.source == source)
        if review_ids is not None:
            if not review_ids:
                return []
            statement = statement.where(AuditReviewORM.id.in_(review_ids))
        records = (await self.session.scalars(statement)).all()
        query = search.strip().lower()
        output = []
        for record in records:
            version = self._version_for_review(record, result_version)
            if not version:
                continue
            result = parse_audit_result(version.payload_json)
            if outcome != "all" and result.overall_outcome != outcome:
                continue
            searchable = " ".join(
                [
                    record.id,
                    str((record.input_json or {}).get("claim_number") or ""),
                    record.source,
                    result.title,
                    result.description,
                    result.overall_outcome,
                    result.outcome_justification,
                    version.compact_text,
                ]
            ).lower()
            if query and query not in searchable:
                continue
            output.append(record)
        return output

    async def _feedback_summaries(
        self,
        review_ids: list[str],
        *,
        enabled: bool,
    ) -> dict[str, dict[str, Any]]:
        if not enabled or not review_ids:
            return {}
        records = (
            await self.session.scalars(
                select(FeedbackORM)
                .where(FeedbackORM.review_id.in_(review_ids))
                .order_by(FeedbackORM.review_id.asc(), FeedbackORM.created_at.asc())
            )
        ).all()
        grouped: dict[str, list[FeedbackORM]] = {}
        for record in records:
            grouped.setdefault(record.review_id, []).append(record)

        summaries: dict[str, dict[str, Any]] = {}
        for review_id, feedback_rows in grouped.items():
            scores = [row.rating for row in feedback_rows]
            comments = [
                str(row.comment).strip()
                for row in feedback_rows
                if row.comment and str(row.comment).strip()
            ]
            latest = max(feedback_rows, key=lambda row: row.created_at)
            summaries[review_id] = {
                "count": len(feedback_rows),
                "average_score": sum(scores) / len(scores) if scores else None,
                "min_score": min(scores) if scores else None,
                "latest_score": latest.rating,
                "latest_comment": latest.comment,
                "latest_at": latest.created_at,
                "comments": comments,
            }
        return summaries

    def _filter_reviews_by_feedback(
        self,
        reviews: list[AuditReviewORM],
        feedback_summaries: dict[str, dict[str, Any]],
        feedback_filter: str,
    ) -> list[AuditReviewORM]:
        if feedback_filter == "all":
            return reviews
        output: list[AuditReviewORM] = []
        for review in reviews:
            summary = feedback_summaries.get(review.id)
            count = int((summary or {}).get("count") or 0)
            min_score = (summary or {}).get("min_score")
            if feedback_filter == "with_feedback" and count > 0:
                output.append(review)
            elif feedback_filter == "without_feedback" and count == 0:
                output.append(review)
            elif feedback_filter == "low_score" and isinstance(min_score, int | float):
                if min_score <= 2:
                    output.append(review)
        return output

    def _version_for_review(
        self,
        review: AuditReviewORM,
        result_version: str,
    ) -> AuditResultVersionORM | None:
        version_id = (
            review.original_result_version_id
            if result_version == "original"
            else review.current_user_result_version_id or review.original_result_version_id
        )
        if not version_id:
            return None
        versions = {version.id: version for version in review.versions}
        return versions.get(version_id)

    def _review_to_source_row(
        self,
        review: AuditReviewORM,
        result_version: str,
        *,
        feedback_summary: dict[str, Any] | None = None,
    ) -> DatasetSourceRowRecord:
        version = self._version_for_review(review, result_version)
        if version is None:
            raise ValueError(f"Review {review.id} does not have a {result_version} result.")
        result = parse_audit_result(version.payload_json)
        metrics = _candidate_metrics(result)
        input_json = review.input_json or {}
        return DatasetSourceRowRecord(
            source_record_id=f"{review.id}:{version.id}",
            review_id=review.id,
            source_id="app_db_reviews",
            source_kind="app_db_reviews",
            source_label="Application DB Reviews",
            result_version=result_version,  # type: ignore[arg-type]
            source=review.source,
            claim_number=str(input_json.get("claim_number") or ""),
            effective_date=str(input_json.get("effective_date") or "") or None,
            title=result.title,
            outcome=result.overall_outcome,
            issue_count=int(metrics["issue_count"]),
            driver_count=int(metrics["driver_count"]),
            total_amount_reviewed_dollars=metrics["total_amount_reviewed_dollars"],
            total_overwrite_dollars=metrics["total_overwrite_dollars"],
            total_underwrite_dollars=metrics["total_underwrite_dollars"],
            feedback_count=int((feedback_summary or {}).get("count") or 0),
            feedback_average_score=feedback_summary.get("average_score")
            if feedback_summary
            else None,
            feedback_min_score=feedback_summary.get("min_score") if feedback_summary else None,
            feedback_latest_score=feedback_summary.get("latest_score")
            if feedback_summary
            else None,
            feedback_latest_comment=feedback_summary.get("latest_comment")
            if feedback_summary
            else None,
            feedback_latest_at=feedback_summary.get("latest_at") if feedback_summary else None,
            created_at=review.created_at,
            updated_at=review.updated_at,
        )

    def _review_to_candidate(
        self,
        review: AuditReviewORM,
        result_version: str,
        *,
        feedback_summary: dict[str, Any] | None = None,
    ) -> CanonicalDatasetCandidate:
        version = self._version_for_review(review, result_version)
        if version is None:
            raise ValueError(f"Review {review.id} does not have a {result_version} result.")
        result = parse_audit_result(version.payload_json)
        input_json = review.input_json or {}
        claim_number = str(input_json.get("claim_number") or review.id[:8])
        instructions = str(input_json.get("instructions") or input_json.get("prompt") or "")
        metadata: dict[str, Any] = {
            "review_id": review.id,
            "result_version_id": version.id,
            "result_version": result_version,
            "source": review.source,
            "created_at": review.created_at.isoformat() if review.created_at else None,
            "updated_at": review.updated_at.isoformat() if review.updated_at else None,
        }
        if feedback_summary and int(feedback_summary.get("count") or 0) > 0:
            metadata["feedback"] = {
                "count": int(feedback_summary.get("count") or 0),
                "average_score": feedback_summary.get("average_score"),
                "min_score": feedback_summary.get("min_score"),
                "latest_score": feedback_summary.get("latest_score"),
                "latest_comment": feedback_summary.get("latest_comment"),
                "latest_at": (
                    feedback_summary["latest_at"].isoformat()
                    if feedback_summary.get("latest_at")
                    else None
                ),
                "comments": feedback_summary.get("comments") or [],
                "captured_from_review_id": review.id,
            }
        tags = ["app-db", review.source]
        if metadata.get("feedback"):
            tags.append("feedback")
            min_score = (metadata["feedback"] or {}).get("min_score")
            if isinstance(min_score, int | float) and min_score <= 2:
                tags.append("low-feedback-score")

        return CanonicalDatasetCandidate(
            source_key="app_db_reviews",
            source_kind="app_db_reviews",
            source_label="Application DB Reviews",
            source_record_id=f"{review.id}:{version.id}",
            claim_number=claim_number,
            effective_date=str(input_json.get("effective_date") or "") or None,
            instructions=instructions,
            input={
                **input_json,
                "source_review_id": review.id,
                "source_result_version_id": version.id,
                "source_result_version": result_version,
            },
            references=[
                DatasetReference(
                    reference_kind="R2",
                    result=result,
                    reviewer="app-db",
                    source_metadata={
                        "review_id": review.id,
                        "result_version_id": version.id,
                        "result_version": result_version,
                        "source": review.source,
                    },
                )
            ],
            metadata=metadata,
            tags=tags,
        )

    async def _population_to_schema(
        self,
        population: DatasetPopulationORM,
    ) -> DatasetPopulationRecord:
        candidate_count = await self.session.scalar(
            select(func.count(DatasetCandidateORM.id)).where(
                DatasetCandidateORM.population_id == population.id
            )
        )
        included_count = await self.session.scalar(
            select(func.count(DatasetCandidateORM.id)).where(
                DatasetCandidateORM.population_id == population.id,
                DatasetCandidateORM.included.is_(True),
            )
        )
        clustered_count = await self.session.scalar(
            select(func.count(DatasetCandidateORM.id)).where(
                DatasetCandidateORM.population_id == population.id,
                DatasetCandidateORM.cluster_id.is_not(None),
            )
        )
        candidates = await self._candidate_rows(population.id)
        r1_count = sum(
            1
            for candidate in candidates
            if any(
                reference.get("reference_kind") == "R1" for reference in candidate.references_json
            )
        )
        r2_count = sum(
            1
            for candidate in candidates
            if any(
                reference.get("reference_kind") == "R2" for reference in candidate.references_json
            )
        )
        return DatasetPopulationRecord(
            id=population.id,
            name=population.name,
            description=population.description,
            form_id=population.form_id,
            form_version=population.form_version,
            form_kind=population.form_kind,  # type: ignore[arg-type]
            status=population.status,  # type: ignore[arg-type]
            source_config=population.source_config_json,
            cluster_config=population.cluster_config_json,
            sample_config=population.sample_config_json,
            published_dataset_id=population.published_dataset_id,
            candidate_count=candidate_count or 0,
            included_count=included_count or 0,
            clustered_count=clustered_count or 0,
            r1_count=r1_count,
            r2_count=r2_count,
            created_at=population.created_at,
            updated_at=population.updated_at,
        )

    def _candidate_to_schema(self, candidate: DatasetCandidateORM) -> DatasetCandidateRecord:
        return DatasetCandidateRecord(
            id=candidate.id,
            population_id=candidate.population_id,
            source_kind=candidate.source_kind,
            source_key=candidate.source_key,
            source_label=candidate.source_label,
            source_record_id=candidate.source_record_id,
            dedupe_key=candidate.dedupe_key,
            claim_number=candidate.claim_number,
            effective_date=candidate.effective_date,
            instructions=candidate.instructions,
            input=candidate.input_json or {},
            references=[
                DatasetReference.model_validate(reference)
                for reference in candidate.references_json or []
            ],
            metadata=candidate.metadata_json,
            tags=candidate.tags_json or [],
            metrics=candidate.metrics_json or {},
            included=candidate.included,
            cluster_id=candidate.cluster_id,
            cluster_distance=candidate.cluster_distance,
            cluster_score=candidate.cluster_score,
            cluster_metadata=candidate.cluster_metadata_json,
            sample_reason=candidate.sample_reason,
            created_at=candidate.created_at,
            updated_at=candidate.updated_at,
        )

    async def _candidate_rows(self, population_id: str) -> list[DatasetCandidateORM]:
        return (
            await self.session.scalars(
                select(DatasetCandidateORM)
                .where(DatasetCandidateORM.population_id == population_id)
                .order_by(DatasetCandidateORM.created_at.asc())
            )
        ).all()

    async def _get_population_orm(self, population_id: str) -> DatasetPopulationORM:
        population = await self.session.get(DatasetPopulationORM, population_id)
        if not population:
            raise KeyError(f"Unknown dataset population: {population_id}")
        return population

    async def _get_candidate_orm(self, candidate_id: str) -> DatasetCandidateORM:
        candidate = await self.session.get(DatasetCandidateORM, candidate_id)
        if not candidate:
            raise KeyError(f"Unknown dataset candidate: {candidate_id}")
        return candidate
