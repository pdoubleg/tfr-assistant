"""Reset local dev data and seed standard plus financial audit examples.

Run from ``backend`` after applying migrations:

    uv run python scripts/reseed_dev_financial_forms.py

This is intentionally a development helper. It clears reviews, batches, evals, and
optimization runs so the local projection tables match the current schema.
"""

from __future__ import annotations

import asyncio
import sys
from decimal import Decimal
from pathlib import Path

from sqlalchemy import delete

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings
from app.db.models import (
    AuditBatchORM,
    AuditBatchTemplateORM,
    AuditResultItemORM,
    AuditResultTextORM,
    AuditResultVersionORM,
    AuditReviewORM,
    EvalAgreementItemORM,
    EvalCaseORM,
    EvalComparisonORM,
    EvalDatasetORM,
    EvalGroundTruthORM,
    EvalRunItemORM,
    EvalRunORM,
    EvaluationORM,
    FeedbackORM,
    OptimizationCandidateORM,
    OptimizationEventORM,
    OptimizationRunORM,
)
from app.db.session import AsyncSessionLocal
from app.models.audit import AuditFormResult, AuditFormWithFinancialsResult
from app.schemas.evaluations import EvalCaseCreate, EvalDatasetCreate
from app.services.catalog import FormCatalog
from app.services.evaluation_service import EvaluationRepository
from app.services.review_repository import ReviewRepository


DELETE_ORDER = [
    OptimizationEventORM,
    OptimizationCandidateORM,
    OptimizationRunORM,
    EvalAgreementItemORM,
    EvalComparisonORM,
    EvalRunItemORM,
    EvalRunORM,
    EvalGroundTruthORM,
    EvalCaseORM,
    EvalDatasetORM,
    FeedbackORM,
    EvaluationORM,
    AuditResultItemORM,
    AuditResultTextORM,
    AuditResultVersionORM,
    AuditReviewORM,
    AuditBatchORM,
    AuditBatchTemplateORM,
]


def _standard_sample(canonical: AuditFormResult, index: int) -> AuditFormResult:
    questions = []
    failing = index % 2 == 1
    for question in canonical.questions:
        sub_questions = question.sub_questions or []
        if sub_questions:
            updated_subs = [
                sub_question.model_copy(
                    update={
                        "answer": failing and sub_index == 0,
                        "reasoning": (
                            f"Synthetic driver evidence for {sub_question.id}."
                            if failing and sub_index == 0
                            else ""
                        ),
                        "citations": "Synthetic claim note." if failing and sub_index == 0 else "",
                    }
                )
                for sub_index, sub_question in enumerate(sub_questions)
            ]
            questions.append(
                question.model_copy(
                    update={
                        "answer": "No" if failing else "Yes",
                        "comments": None,
                        "citations": None,
                        "sub_questions": updated_subs,
                    }
                )
            )
        else:
            questions.append(
                question.model_copy(
                    update={
                        "answer": "No" if failing else "Yes",
                        "comments": (
                            "Synthetic sample found missing support."
                            if failing
                            else "Synthetic sample support is complete."
                        ),
                        "citations": "Synthetic claim note.",
                        "sub_questions": None,
                    }
                )
            )
    return canonical.model_copy(
        deep=True,
        update={
            "questions": questions,
            "overall_outcome": "Does Not Meet" if failing else "Meets",
            "outcome_justification": (
                "Synthetic sample has one or more standard audit exceptions."
                if failing
                else "Synthetic sample satisfies the standard audit form."
            ),
        },
    )


def _financial_sample(
    canonical: AuditFormWithFinancialsResult,
    index: int,
) -> AuditFormWithFinancialsResult:
    total_reviewed = Decimal("10000.00") + Decimal(index * 2500)
    questions = []
    for q_index, question in enumerate(canonical.questions, start=1):
        overwrite = Decimal("125.50") * index if q_index == 1 else Decimal("0.00")
        underwrite = Decimal("85.25") * index if q_index == 2 else Decimal("0.00")
        has_exception = overwrite > 0 or underwrite > 0
        questions.append(
            question.model_copy(
                update={
                    "answer": "No" if has_exception else "Yes",
                    "comments": (
                        "Synthetic financial exception identified."
                        if has_exception
                        else "No financial exception identified."
                    ),
                    "citations": "Synthetic payment and estimate records.",
                    "overwrite_dollars": overwrite,
                    "underwrite_dollars": underwrite,
                }
            )
        )
    return canonical.model_copy(
        deep=True,
        update={
            "total_amount_reviewed_dollars": total_reviewed,
            "questions": questions,
            "overall_outcome": "Does Not Meet" if index else "Meets",
            "outcome_justification": (
                "Synthetic financial audit has overwrite or underwrite exceptions."
                if index
                else "Synthetic financial audit has no financial exceptions."
            ),
        },
    )


async def _clear_dev_data() -> None:
    async with AsyncSessionLocal() as session:
        for model in DELETE_ORDER:
            await session.execute(delete(model))
        await session.commit()


async def _seed_reviews_and_datasets() -> None:
    settings = get_settings()
    catalog = FormCatalog(settings.form_catalog_dir)
    standard = catalog.get_form("tfr_default", "v0.2")
    financial = catalog.get_form("financial_claim_review", "v0.1")

    standard_results = [
        _standard_sample(standard.canonical, index)
        for index in range(4)
        if isinstance(standard.canonical, AuditFormResult)
    ]
    financial_results = [
        _financial_sample(financial.canonical, index)
        for index in range(4)
        if isinstance(financial.canonical, AuditFormWithFinancialsResult)
    ]

    async with AsyncSessionLocal() as session:
        repository = ReviewRepository(session)
        for index, result in enumerate([*standard_results, *financial_results], start=1):
            await repository.create_from_agent_output(
                result,
                source="synthetic",
                input_json={
                    "claim_number": f"DEV-{index:03d}",
                    "generation_prompt": "Local reseed synthetic sample.",
                },
            )

    async with AsyncSessionLocal() as session:
        eval_repository = EvaluationRepository(session)
        await eval_repository.create_dataset(
            EvalDatasetCreate(
                name="Dev Standard Audit Samples",
                description="Temporary local standard audit eval samples.",
                form_id=standard.id,
                form_version=standard.version,
                form_kind="standard",
                source_kind="dev_reseed",
                cases=[
                    EvalCaseCreate(
                        claim_number=f"STD-EVAL-{index + 1:03d}",
                        effective_date="2026-05-30",
                        instructions="Synthetic standard eval case.",
                        input={"prompt": "Synthetic standard eval case."},
                        ground_truths=[
                            {
                                "reference_kind": "R2",
                                "result": result,
                                "reviewer": "dev-reseed",
                            }
                        ],
                    )
                    for index, result in enumerate(standard_results[:2])
                ],
            )
        )
        await eval_repository.create_dataset(
            EvalDatasetCreate(
                name="Dev Financial Audit Samples",
                description="Temporary local financial audit eval samples.",
                form_id=financial.id,
                form_version=financial.version,
                form_kind="financial",
                source_kind="dev_reseed",
                cases=[
                    EvalCaseCreate(
                        claim_number=f"FIN-EVAL-{index + 1:03d}",
                        effective_date="2026-05-30",
                        instructions="Synthetic financial eval case.",
                        input={"prompt": "Synthetic financial eval case."},
                        ground_truths=[
                            {
                                "reference_kind": "R2",
                                "result": result,
                                "reviewer": "dev-reseed",
                            }
                        ],
                    )
                    for index, result in enumerate(financial_results[:2])
                ],
            )
        )


async def main() -> None:
    await _clear_dev_data()
    await _seed_reviews_and_datasets()
    print("Reseeded local dev reviews and eval datasets for standard and financial forms.")


if __name__ == "__main__":
    asyncio.run(main())
