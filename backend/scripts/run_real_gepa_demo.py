from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.session import AsyncSessionLocal, init_db
from app.schemas.optimizations import (
    OptimizationGepaParams,
    OptimizationRunCreate,
    OptimizationTraceConfig,
)
from app.services.optimization_service import (
    DEMO_FORM_ID,
    DEMO_FORM_VERSION,
    OptimizationRepository,
    OptimizationRunService,
    apply_split_helper,
    ensure_demo_fixture,
)


async def _prepare_run() -> str:
    await init_db()
    fixture = await ensure_demo_fixture()
    async with AsyncSessionLocal() as session:
        repository = OptimizationRepository(session)
        cases = await repository.list_cases(
            form_id=DEMO_FORM_ID,
            form_version=DEMO_FORM_VERSION,
            include_demo=True,
        )
        if len(cases) < 20:
            raise RuntimeError(f"Expected 20 demo cases, found {len(cases)}.")

        metric_mode = (
            "comparison_with_judge"
            if os.getenv("RUN_REAL_GEPA_DEMO_JUDGE") == "1"
            else "comparison"
        )
        request = OptimizationRunCreate(
            name="Real LLM GEPA receipt demo",
            form_id=fixture.form_id,
            form_version=fixture.form_version,
            seed_instruction_source="manual",
            manual_instructions=(
                "Review the receipt note and decide whether the reimbursement is acceptable. "
                "Answer the form questions with brief reasoning."
            ),
            metric_mode=metric_mode,
            score_key=os.getenv("RUN_REAL_GEPA_DEMO_SCORE_KEY", "score"),  # type: ignore[arg-type]
            reference_policy="prefer_r2",
            judge_model=os.getenv("RUN_REAL_GEPA_DEMO_JUDGE_MODEL") or None,
            gepa_params=OptimizationGepaParams(
                max_metric_calls=int(os.getenv("RUN_REAL_GEPA_DEMO_MAX_CALLS", "8")),
                reflection_minibatch_size=int(os.getenv("RUN_REAL_GEPA_DEMO_MINIBATCH", "3")),
                seed=int(os.getenv("RUN_REAL_GEPA_DEMO_SEED", "7")),
                track_best_outputs=True,
            ),
            trace_config=OptimizationTraceConfig(
                capture_traces=True,
                include_debug_traces=True,
                include_thinking=True,
                max_tool_return_chars=int(os.getenv("RUN_REAL_GEPA_DEMO_TOOL_CHARS", "1200")),
            ),
            case_splits=apply_split_helper(
                cases,
                mode="stratified_outcome_issues",
                seed=int(os.getenv("RUN_REAL_GEPA_DEMO_SPLIT_SEED", "7")),
            ),
        )
        run = await repository.create_run(request)
        return run.id


async def _load_summary(run_id: str) -> str:
    async with AsyncSessionLocal() as session:
        run = await OptimizationRepository(session).get_run(run_id)
        artifact_map = run.artifacts or {}
        has_best_instructions = bool(run.best_candidate and run.best_candidate.get("instructions"))
        return (
            f"run_id={run.id}\n"
            f"status={run.status}\n"
            f"best_score={run.best_score}\n"
            f"metric_calls={run.total_metric_calls}\n"
            f"best_instructions={has_best_instructions}\n"
            f"dag={artifact_map.get('dag')}\n"
            f"native_html={artifact_map.get('native_html')}\n"
            f"report={artifact_map.get('report')}\n"
        )


def main() -> int:
    if os.getenv("RUN_REAL_GEPA_DEMO") != "1":
        print("Set RUN_REAL_GEPA_DEMO=1 to run the real LLM GEPA receipt demo.")
        return 0

    run_id = asyncio.run(_prepare_run())
    print(f"Created optimization run {run_id}. Starting GEPA...")
    OptimizationRunService().run(run_id)
    print(asyncio.run(_load_summary(run_id)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
