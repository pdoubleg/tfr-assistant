from __future__ import annotations

import asyncio
import json
import logging
import math
from datetime import datetime
from typing import Any
from uuid import uuid4

import gepa.api
from gepa.core.result import GEPAResult
from gepa.gepa_utils import find_dominator_programs
from sqlalchemy import delete, select

from app.agents.review_agent import DEFAULT_REVIEW_INSTRUCTIONS, build_file_review_agent
from app.core.config import Settings, get_settings
from app.core.llm import LLMModelConfig
from app.db.models import (
    EvalCaseORM,
    EvalGroundTruthORM,
    OptimizationCandidateORM,
    OptimizationEventORM,
    OptimizationRunORM,
)
from app.db.session import AsyncSessionLocal
from app.models.audit import AuditFormResult
from app.schemas.optimizations import OptimizationGepaParams, OptimizationRunCreate
from app.services.catalog import FormCatalog
from app.services.optimization.adapter import TFRGepaAdapter
from app.services.optimization.artifacts import (
    CancelFileStopper,
    OptimizationArtifactWriter,
    OptimizationRunCallback,
)
from app.services.optimization.components import seed_candidate_from_instructions
from app.services.optimization.models import OptimizationDataInstance, OptimizationRolloutOutput
from app.services.optimization.repository import prompt_from_case
from app.services.optimization.utils import now_utc

logger = logging.getLogger(__name__)

AUTO_RUN_SETTINGS = {
    "light": {"n": 6},
    "medium": {"n": 12},
    "heavy": {"n": 18},
}


def auto_budget(
    num_candidates: int,
    valset_size: int,
    minibatch_size: int = 35,
    full_eval_steps: int = 5,
    num_preds: int = 1,
) -> int:
    """Estimate metric calls using DSPy's GEPA auto-budget formula."""
    num_trials = int(max(2 * (num_preds * 2) * math.log2(num_candidates), 1.5 * num_candidates))
    if num_trials < 0 or valset_size < 0 or minibatch_size < 0:
        raise ValueError("num_trials, valset_size, and minibatch_size must be >= 0.")
    if full_eval_steps < 1:
        raise ValueError("full_eval_steps must be >= 1.")

    total = valset_size
    total += num_candidates * 5
    total += num_trials * minibatch_size
    if num_trials == 0:
        return total

    periodic_fulls = (num_trials + 1) // full_eval_steps + 1
    extra_final = 1 if num_trials < full_eval_steps else 0
    total += (periodic_fulls + extra_final) * valset_size
    return total


def estimate_metric_budget(
    params: OptimizationGepaParams,
    *,
    train_count: int,
    val_count: int,
) -> int:
    if params.max_metric_calls is not None:
        return params.max_metric_calls
    if params.auto is not None:
        return auto_budget(
            num_candidates=AUTO_RUN_SETTINGS[params.auto]["n"],
            valset_size=val_count if val_count else train_count,
        )
    if params.max_full_evals is not None:
        return params.max_full_evals * (train_count + val_count)
    raise ValueError("No GEPA budget option is set.")


def budget_mode(params: OptimizationGepaParams) -> str:
    if params.max_metric_calls is not None:
        return "max_metric_calls"
    if params.max_full_evals is not None:
        return "max_full_evals"
    if params.auto is not None:
        return "auto"
    return "unknown"


class OptimizationRunService:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def run(self, run_id: str) -> None:
        asyncio.run(self._run_async(run_id))

    async def _run_async(self, run_id: str) -> None:
        async with AsyncSessionLocal() as session:
            run = await session.get(OptimizationRunORM, run_id)
            if not run:
                return
            request = OptimizationRunCreate.model_validate(run.config_json)
            run.status = "running"
            run.started_at = run.started_at or now_utc()
            run.completed_at = None
            run.error_message = None
            run.updated_at = now_utc()
            writer = OptimizationArtifactWriter(run.id, self.settings.optimization_runs_dir)
            run.artifacts_json = {"run_dir": str(writer.run_dir), **writer.artifact_map()}
            session.add(run)
            await session.commit()

        writer = OptimizationArtifactWriter(run_id, self.settings.optimization_runs_dir)
        try:
            await asyncio.to_thread(self._execute_sync, run_id, request, writer)
        except Exception as exc:
            logger.exception("Optimization run failed")
            writer.append_event(
                "run_error",
                str(exc),
                level="error",
                data={"exception_type": type(exc).__name__},
            )
            async with AsyncSessionLocal() as session:
                run = await session.get(OptimizationRunORM, run_id)
                if run:
                    run.status = "failed"
                    run.error_message = str(exc)
                    run.completed_at = now_utc()
                    run.updated_at = now_utc()
                    session.add(run)
                    await session.commit()
            await self._persist_events(run_id, writer.events_path)

    def _execute_sync(
        self,
        run_id: str,
        request: OptimizationRunCreate,
        writer: OptimizationArtifactWriter,
    ) -> None:
        catalog = FormCatalog(self.settings.form_catalog_dir)
        definition = catalog.get_form(request.form_id, request.form_version)
        form_path = catalog.path_for(request.form_id, request.form_version)
        if request.seed_instruction_source == "manual":
            seed_instructions = request.manual_instructions
        elif request.seed_instruction_source == "prompt_registry" and request.resolved_seed_prompt:
            seed_instructions = request.resolved_seed_prompt.text
        else:
            seed_instructions = definition.instructions or DEFAULT_REVIEW_INSTRUCTIONS
        seed_candidate = seed_candidate_from_instructions(seed_instructions)

        instances = asyncio.run(self._load_instances(request, definition, str(form_path)))
        trainset = [item for item in instances if item.split == "train"]
        valset = [item for item in instances if item.split == "val"]
        testset = [item for item in instances if item.split == "test"]
        max_metric_calls = estimate_metric_budget(
            request.gepa_params,
            train_count=len(trainset),
            val_count=len(valset),
        )
        module_selector = "all"
        proposer_model = self._model_config_for(request.gepa_params.reflection_model)
        judge_model = (
            self._model_config_for(request.judge_model)
            if request.metric_mode == "comparison_with_judge"
            else None
        )
        adapter = TFRGepaAdapter(
            agent=build_file_review_agent(self.settings),
            config=request,
            trace_config=request.trace_config,
            artifact_writer=writer,
            proposer_model_config=proposer_model,
            judge_model_config=judge_model,
        )
        callback = OptimizationRunCallback(writer)
        writer.append_event(
            "run_prepared",
            "Optimization run prepared",
            data={
                "train_count": len(trainset),
                "val_count": len(valset),
                "test_count": len(testset),
                "seed_instruction_source": request.seed_instruction_source,
                "budget_mode": budget_mode(request.gepa_params),
                "estimated_metric_calls": max_metric_calls,
                "module_selector": module_selector,
            },
        )
        asyncio.run(self._save_seed(run_id, seed_candidate))
        raw_result: GEPAResult[OptimizationRolloutOutput, Any] = gepa.api.optimize(
            adapter=adapter,
            seed_candidate=seed_candidate,
            trainset=trainset,
            valset=valset,
            max_metric_calls=max_metric_calls,
            candidate_selection_strategy=request.gepa_params.candidate_selection_strategy,  # type: ignore[arg-type]
            frontier_type="instance",
            skip_perfect_score=True,
            batch_sampler=request.gepa_params.batch_sampler,  # type: ignore[arg-type]
            reflection_minibatch_size=request.gepa_params.reflection_minibatch_size,
            perfect_score=1.0,
            module_selector=module_selector,
            use_merge=request.gepa_params.use_merge,
            max_merge_invocations=request.gepa_params.max_merge_invocations,
            merge_val_overlap_floor=request.gepa_params.merge_val_overlap_floor,
            callbacks=[callback],
            stop_callbacks=CancelFileStopper(writer),
            run_dir=str(writer.run_dir),
            use_mlflow=request.gepa_params.use_mlflow,
            mlflow_tracking_uri=request.gepa_params.mlflow_tracking_uri,
            mlflow_experiment_name=request.gepa_params.mlflow_experiment_name,
            track_best_outputs=False,
            display_progress_bar=request.gepa_params.display_progress_bar,
            cache_evaluation=request.gepa_params.cache_evaluation,
            seed=request.gepa_params.seed,
            raise_on_exception=request.gepa_params.raise_on_exception,
            val_evaluation_policy=request.gepa_params.val_evaluation_policy,
        )
        best_idx = raw_result.best_idx
        best_candidate = (
            raw_result.candidates[best_idx] if raw_result.candidates else seed_candidate
        )
        best_score = (
            raw_result.val_aggregate_scores[best_idx]
            if raw_result.val_aggregate_scores and best_idx < len(raw_result.val_aggregate_scores)
            else None
        )
        original_score = (
            raw_result.val_aggregate_scores[0] if raw_result.val_aggregate_scores else None
        )
        test_report = self._evaluate_testset(adapter, testset, best_candidate)
        dag_payload = dag_payload_from_result(raw_result, request, test_report)
        writer.write_json(writer.dag_path, dag_payload)
        writer.write_json(writer.report_path, test_report)
        try:
            from gepa.visualization import candidate_tree_html_from_data

            writer.write_text(
                writer.native_html_path,
                candidate_tree_html_from_data(
                    raw_result.candidates,
                    raw_result.parents,
                    raw_result.val_aggregate_scores,
                    raw_result.per_val_instance_best_candidates,
                ),
            )
        except Exception as exc:
            writer.append_event(
                "artifact_warning",
                f"Native GEPA visualization could not be created: {exc}",
                level="warning",
            )
        completed_status = "canceled" if writer.is_cancel_requested() else "completed"
        asyncio.run(
            self._finalize_run(
                run_id,
                status=completed_status,
                raw_result=raw_result,
                seed_candidate=seed_candidate,
                best_candidate=best_candidate,
                best_score=best_score,
                original_score=original_score,
                token_usage=adapter.token_usage,
                metrics={"test": test_report, "dag": {"node_count": len(dag_payload["nodes"])}},
                artifacts={"run_dir": str(writer.run_dir), **writer.artifact_map()},
            )
        )
        asyncio.run(self._persist_events(run_id, writer.events_path))

    def _evaluate_testset(
        self,
        adapter: TFRGepaAdapter,
        testset: list[OptimizationDataInstance],
        best_candidate: dict[str, str],
    ) -> dict[str, Any]:
        if not testset:
            return {"count": 0, "average_score": None, "items": []}
        batch = adapter.evaluate(testset, best_candidate, capture_traces=False)
        items = [
            {
                "case_id": instance.case_id,
                "claim_number": instance.claim_number,
                "score": score,
                "success": output.success,
                "feedback": output.feedback,
                "comparison": output.comparison,
            }
            for instance, output, score in zip(
                testset,
                batch.outputs,
                batch.scores,
                strict=True,
            )
        ]
        return {
            "count": len(items),
            "average_score": sum(batch.scores) / len(batch.scores) if batch.scores else None,
            "items": items,
        }

    def _model_config_for(self, model_name: str | None) -> LLMModelConfig:
        config = self.settings.chat_llm_config()
        if model_name and model_name.strip():
            config.model_name = model_name.strip()
        return config

    async def _load_instances(
        self,
        request: OptimizationRunCreate,
        definition: Any,
        form_path: str,
    ) -> list[OptimizationDataInstance]:
        split_by_case = {item.case_id: item.split for item in request.case_splits}
        async with AsyncSessionLocal() as session:
            cases = (
                await session.scalars(
                    select(EvalCaseORM).where(EvalCaseORM.id.in_(split_by_case.keys()))
                )
            ).all()
            instances: list[OptimizationDataInstance] = []
            for case in cases:
                truths = (
                    await session.scalars(
                        select(EvalGroundTruthORM)
                        .where(EvalGroundTruthORM.case_id == case.id)
                        .order_by(EvalGroundTruthORM.reference_kind.asc())
                    )
                ).all()
                references = [
                    (
                        truth.reference_kind,
                        AuditFormResult.model_validate(truth.payload_json),
                    )
                    for truth in truths
                ]
                instances.append(
                    OptimizationDataInstance(
                        case_id=case.id,
                        claim_number=case.claim_number,
                        effective_date=case.effective_date,
                        instructions=case.instructions,
                        user_prompt=prompt_from_case(case),
                        form_path=form_path,
                        tools=list(definition.tools or []),
                        knowledge_docs=list(definition.knowledge_docs or []),
                        references=references,
                        split=split_by_case[case.id],
                        metadata=case.input_json or {},
                    )
                )
        return instances

    async def _save_seed(self, run_id: str, seed_candidate: dict[str, str]) -> None:
        async with AsyncSessionLocal() as session:
            run = await session.get(OptimizationRunORM, run_id)
            if run:
                run.seed_candidate_json = seed_candidate
                run.updated_at = now_utc()
                session.add(run)
                await session.commit()

    async def _finalize_run(
        self,
        run_id: str,
        *,
        status: str,
        raw_result: GEPAResult[OptimizationRolloutOutput, Any],
        seed_candidate: dict[str, str],
        best_candidate: dict[str, str],
        best_score: float | None,
        original_score: float | None,
        token_usage: dict[str, int],
        metrics: dict[str, Any],
        artifacts: dict[str, Any],
    ) -> None:
        async with AsyncSessionLocal() as session:
            run = await session.get(OptimizationRunORM, run_id)
            if not run:
                return
            await session.execute(
                delete(OptimizationCandidateORM).where(OptimizationCandidateORM.run_id == run_id)
            )
            dominators = set(
                find_dominator_programs(
                    raw_result.per_val_instance_best_candidates,
                    raw_result.val_aggregate_scores,
                )
                if raw_result.val_aggregate_scores
                else []
            )
            best_idx = raw_result.best_idx if raw_result.candidates else 0
            for index, candidate in enumerate(raw_result.candidates):
                if index == best_idx:
                    candidate_status = "best"
                elif index in dominators:
                    candidate_status = "pareto"
                elif index == 0:
                    candidate_status = "seed"
                else:
                    candidate_status = "candidate"
                session.add(
                    OptimizationCandidateORM(
                        id=str(uuid4()),
                        run_id=run_id,
                        candidate_index=index,
                        parent_indices_json=raw_result.parents[index],
                        status=candidate_status,
                        candidate_json=candidate,
                        score=raw_result.val_aggregate_scores[index]
                        if index < len(raw_result.val_aggregate_scores)
                        else None,
                        metrics_json=raw_result.val_aggregate_subscores[index]
                        if raw_result.val_aggregate_subscores
                        and index < len(raw_result.val_aggregate_subscores)
                        else None,
                        created_at=now_utc(),
                    )
                )
            run.status = status
            run.seed_candidate_json = seed_candidate
            run.best_candidate_json = best_candidate
            run.best_score = best_score
            run.original_score = original_score
            run.total_metric_calls = raw_result.total_metric_calls or 0
            run.token_usage_json = token_usage
            run.metrics_json = metrics
            run.artifacts_json = artifacts
            run.completed_at = now_utc()
            run.updated_at = now_utc()
            session.add(run)
            await session.commit()

    async def _persist_events(self, run_id: str, events_path) -> None:
        if not events_path.exists():
            return
        async with AsyncSessionLocal() as session:
            await session.execute(
                delete(OptimizationEventORM).where(OptimizationEventORM.run_id == run_id)
            )
            for line in events_path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                payload = json.loads(line)
                session.add(
                    OptimizationEventORM(
                        id=payload.get("id") or str(uuid4()),
                        run_id=run_id,
                        sequence=int(payload.get("sequence") or 0),
                        event_type=str(payload.get("type") or "event"),
                        payload_json=payload,
                        created_at=datetime.fromisoformat(payload["created_at"])
                        if payload.get("created_at")
                        else now_utc(),
                    )
                )
            await session.commit()


def dag_payload_from_result(
    raw_result: GEPAResult[OptimizationRolloutOutput, Any],
    request: OptimizationRunCreate,
    test_report: dict[str, Any],
) -> dict[str, Any]:
    candidates = raw_result.candidates or []
    scores = raw_result.val_aggregate_scores or []
    dominators = (
        set(find_dominator_programs(raw_result.per_val_instance_best_candidates, scores))
        if scores
        else set()
    )
    best_idx = raw_result.best_idx if candidates else 0
    nodes = []
    for index, candidate in enumerate(candidates):
        if index == best_idx:
            role = "best"
        elif index in dominators:
            role = "pareto"
        elif index == 0:
            role = "seed"
        else:
            role = "candidate"
        nodes.append(
            {
                "id": str(index),
                "candidate_index": index,
                "role": role,
                "score": scores[index] if index < len(scores) else None,
                "candidate": candidate,
                "parents": raw_result.parents[index] if index < len(raw_result.parents) else [],
            }
        )
    edges = []
    for child, parents in enumerate(raw_result.parents or []):
        for parent in parents:
            if parent is not None:
                edges.append(
                    {"id": f"{parent}-{child}", "source": str(parent), "target": str(child)}
                )
    return {
        "schema_version": 1,
        "nodes": nodes,
        "edges": edges,
        "best_idx": best_idx,
        "pareto_front": sorted(dominators),
        "config": request.model_dump(mode="json"),
        "test_report": test_report,
        "total_metric_calls": raw_result.total_metric_calls,
    }


async def run_optimization_job(run_id: str, settings: Settings | None = None) -> None:
    await asyncio.to_thread(OptimizationRunService(settings or get_settings()).run, run_id)
