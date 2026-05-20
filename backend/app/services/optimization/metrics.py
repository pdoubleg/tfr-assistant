from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.models.audit import AuditFormResult, FormQuestion
from app.services.evaluation_metrics import compare_audit_results


class JudgeFeedback(BaseModel):
    feedback: str = Field(description="Concise feedback for improving the audit prompt.")
    missed_rules: list[str] = Field(default_factory=list)
    overfit_risks: list[str] = Field(default_factory=list)
    judge_score: float | None = Field(default=None, ge=0, le=1)


def issue_count(result: AuditFormResult) -> int:
    return sum(1 for question in result.questions if question.answer != "Yes")


def driver_count(result: AuditFormResult) -> int:
    return sum(
        1 for question in result.questions for sub in question.sub_questions or [] if sub.answer
    )


def score_from_comparison(comparison: dict[str, Any], score_key: str) -> float:
    value = comparison.get(score_key)
    if isinstance(value, int | float):
        return float(value)
    if score_key == "outcome_score" and isinstance(comparison.get("outcome_match"), bool):
        return 1.0 if comparison["outcome_match"] else 0.0
    fallback = comparison.get("score", 0.0)
    return float(fallback) if isinstance(fallback, int | float) else 0.0


def select_references(
    references: list[tuple[str, AuditFormResult]],
    policy: str,
) -> list[tuple[str, AuditFormResult]]:
    if policy == "all":
        return references
    if policy == "r1":
        return [item for item in references if item[0] == "R1"] or references[:1]
    if policy == "r2":
        return [item for item in references if item[0] == "R2"] or references[:1]
    return (
        [item for item in references if item[0] == "R2"]
        or [item for item in references if item[0] == "R1"]
        or references[:1]
    )


def compare_and_score(
    generated: AuditFormResult,
    reference: AuditFormResult,
    *,
    score_key: str,
) -> tuple[float, str, dict[str, Any]]:
    comparison = compare_audit_results(generated=generated, reference=reference)
    score = score_from_comparison(comparison, score_key)
    feedback = format_metric_feedback(
        comparison,
        generated,
        reference,
        score=score,
        score_key=score_key,
    )
    return score, feedback, comparison


def _question_by_id(result: AuditFormResult) -> dict[str, FormQuestion]:
    return {question.id: question for question in result.questions}


def format_metric_feedback(
    comparison: dict[str, Any],
    generated: AuditFormResult,
    reference: AuditFormResult,
    *,
    score: float,
    score_key: str,
) -> str:
    lines = [
        f"Selected score `{score_key}` = {score:.4f}.",
        "Score components:",
    ]
    for key in (
        "score",
        "question_agreement",
        "path_exact_rate",
        "subquestion_f1",
        "outcome_score",
    ):
        value = comparison.get(key)
        if isinstance(value, int | float):
            lines.append(f"- {key}: {float(value):.4f}")
    if not comparison.get("outcome_match", False):
        lines.append(
            "- outcome mismatch: "
            f"generated `{generated.overall_outcome}` vs reference `{reference.overall_outcome}`"
        )
        lines.append(f"  Generated rationale: {generated.outcome_justification}")
        lines.append(f"  Reference rationale: {reference.outcome_justification}")

    generated_questions = _question_by_id(generated)
    reference_questions = _question_by_id(reference)
    question_mismatches = list(comparison.get("question_mismatches", []))
    for question in comparison.get("questions", []):
        question_mismatches.append(
            {
                "id": question.get("id"),
                "text": question.get("text"),
                "generated": question.get("generated_answer"),
                "reference": question.get("reference_answer"),
            }
        )
    for mismatch in question_mismatches:
        _append_question_mismatch(lines, mismatch, generated_questions, reference_questions)

    subquestion_mismatches = list(comparison.get("subquestion_mismatches", []))
    for question in comparison.get("questions", []):
        subquestion_mismatches.extend(question.get("sub_questions") or [])
    for sub_question in subquestion_mismatches:
        _append_subquestion_mismatch(lines, sub_question)
    return "\n".join(lines)


def _append_question_mismatch(
    lines: list[str],
    mismatch: dict[str, Any],
    generated_questions: dict[str, FormQuestion],
    reference_questions: dict[str, FormQuestion],
) -> None:
    question_id = mismatch.get("id")
    generated_question = generated_questions.get(question_id)
    reference_question = reference_questions.get(question_id)
    lines.append(
        f"- {question_id} mismatch: generated `{mismatch.get('generated')}` vs "
        f"reference `{mismatch.get('reference')}`"
    )
    if generated_question and generated_question.comments:
        lines.append(f"  Generated rationale: {generated_question.comments}")
    if reference_question and reference_question.comments:
        lines.append(f"  Reference rationale: {reference_question.comments}")


def _append_subquestion_mismatch(lines: list[str], sub_question: dict[str, Any]) -> None:
    generated_answer = sub_question.get("generated_answer")
    reference_answer = sub_question.get("reference_answer")
    if reference_answer and not generated_answer:
        label = "missed driver"
    elif generated_answer and not reference_answer:
        label = "unexpected driver"
    else:
        label = "driver mismatch"
    lines.append(f"- {label}: {sub_question.get('id')} {sub_question.get('text')}")
    if sub_question.get("generated_reasoning"):
        lines.append(f"  Generated reasoning: {sub_question['generated_reasoning']}")
    if sub_question.get("reference_reasoning"):
        lines.append(f"  Reference reasoning: {sub_question['reference_reasoning']}")
