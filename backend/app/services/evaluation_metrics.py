import json
import math
from typing import Any

import pandas as pd

from app.models.audit import AuditFormResult, FormQuestion, FormSubQuestion

METRIC_SCHEMA_VERSION = 2


def _pct(value: float) -> float:
    return round(value * 100, 2)


def _ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def _f1(precision: float, recall: float) -> float:
    return (2 * precision * recall / (precision + recall)) if precision + recall else 0.0


def _question_map(form: AuditFormResult) -> dict[str, FormQuestion]:
    return {question.id: question for question in form.questions}


def _sub_question_map(question: FormQuestion | None) -> dict[str, FormSubQuestion]:
    if question is None:
        return {}
    return {sub_question.id: sub_question for sub_question in question.sub_questions or []}


def _ordered_question_ids(
    generated_questions: dict[str, FormQuestion],
    reference_questions: dict[str, FormQuestion],
    reference: AuditFormResult,
) -> list[str]:
    question_ids = [question.id for question in reference.questions]
    for question_id in generated_questions:
        if question_id not in reference_questions:
            question_ids.append(question_id)
    return question_ids


def _answer_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def compare_audit_results(
    generated: AuditFormResult,
    reference: AuditFormResult,
) -> dict[str, Any]:
    """Compare a generated audit result to one human reference result.

    Scores are represented as fractions in [0, 1], with matching ``*_percent`` fields
    included for display/reporting convenience.
    """

    generated_questions = _question_map(generated)
    reference_questions = _question_map(reference)
    question_ids = _ordered_question_ids(generated_questions, reference_questions, reference)

    question_matches = 0
    question_true_positive = 0
    question_false_positive = 0
    question_false_negative = 0
    path_exact_matches = 0
    subquestion_eligible_question_count = 0
    subquestion_matches = 0
    subquestion_total = 0
    subquestion_true_positive = 0
    subquestion_false_positive = 0
    subquestion_false_negative = 0
    question_agreements: dict[str, float] = {}
    question_details: list[dict[str, Any]] = []

    for question_id in question_ids:
        generated_question = generated_questions.get(question_id)
        reference_question = reference_questions.get(question_id)
        generated_answer = generated_question.answer if generated_question else None
        reference_answer = reference_question.answer if reference_question else None
        question_match = generated_answer == reference_answer
        question_agreements[question_id] = float(question_match)
        if question_match:
            question_matches += 1

        generated_is_no = generated_answer == "No"
        reference_is_no = reference_answer == "No"
        if generated_is_no and reference_is_no:
            question_true_positive += 1
        elif generated_is_no and not reference_is_no:
            question_false_positive += 1
        elif reference_is_no and not generated_is_no:
            question_false_negative += 1

        generated_sub_questions = _sub_question_map(generated_question)
        reference_sub_questions = _sub_question_map(reference_question)
        sub_question_ids = sorted(generated_sub_questions.keys() | reference_sub_questions.keys())
        subquestion_details = []
        if generated_is_no and reference_is_no:
            subquestion_eligible_question_count += 1

        for sub_question_id in sub_question_ids:
            generated_sub_question = generated_sub_questions.get(sub_question_id)
            reference_sub_question = reference_sub_questions.get(sub_question_id)
            generated_subquestion_answer = (
                bool(generated_sub_question.answer) if generated_sub_question else False
            )
            reference_subquestion_answer = (
                bool(reference_sub_question.answer) if reference_sub_question else False
            )
            subquestion_match = generated_subquestion_answer == reference_subquestion_answer

            if generated_is_no and reference_is_no:
                if subquestion_match:
                    subquestion_matches += 1
                elif generated_subquestion_answer and not reference_subquestion_answer:
                    subquestion_false_positive += 1
                elif reference_subquestion_answer and not generated_subquestion_answer:
                    subquestion_false_negative += 1

                if generated_subquestion_answer and reference_subquestion_answer:
                    subquestion_true_positive += 1

                subquestion_total += 1

            if not subquestion_match:
                subquestion_details.append(
                    {
                        "id": sub_question_id,
                        "text": (reference_sub_question or generated_sub_question).text
                        if (reference_sub_question or generated_sub_question)
                        else "",
                        "generated_answer": generated_subquestion_answer,
                        "reference_answer": reference_subquestion_answer,
                        "generated_reasoning": generated_sub_question.reasoning
                        if generated_sub_question
                        else None,
                        "reference_reasoning": reference_sub_question.reasoning
                        if reference_sub_question
                        else None,
                    }
                )

        path_exact = question_match and not subquestion_details
        if path_exact:
            path_exact_matches += 1

        if not question_match or subquestion_details:
            question_details.append(
                {
                    "id": question_id,
                    "text": (reference_question or generated_question).text
                    if (reference_question or generated_question)
                    else "",
                    "generated_answer": generated_answer,
                    "reference_answer": reference_answer,
                    "sub_questions": subquestion_details,
                }
            )

    question_total = len(question_ids)
    outcome_match = generated.overall_outcome == reference.overall_outcome
    question_agreement = _ratio(question_matches, question_total)
    subquestion_agreement = _ratio(subquestion_matches, subquestion_total)
    path_exact_rate = _ratio(path_exact_matches, question_total)

    question_precision = _ratio(
        question_true_positive,
        question_true_positive + question_false_positive,
    )
    question_recall = _ratio(
        question_true_positive,
        question_true_positive + question_false_negative,
    )
    question_f1 = _f1(question_precision, question_recall)

    subquestion_precision = _ratio(
        subquestion_true_positive,
        subquestion_true_positive + subquestion_false_positive,
    )
    subquestion_recall = _ratio(
        subquestion_true_positive,
        subquestion_true_positive + subquestion_false_negative,
    )
    subquestion_f1 = _f1(subquestion_precision, subquestion_recall)
    form_exact_match = outcome_match and path_exact_matches == question_total

    score = (float(outcome_match) + question_agreement + path_exact_rate + subquestion_f1) / 4

    return {
        "metric_schema_version": METRIC_SCHEMA_VERSION,
        "score": score,
        "score_percent": _pct(score),
        "outcome_match": outcome_match,
        "outcome_score": float(outcome_match),
        "generated_outcome": generated.overall_outcome,
        "reference_outcome": reference.overall_outcome,
        "generated_outcome_justification": generated.outcome_justification,
        "reference_outcome_justification": reference.outcome_justification,
        "question_total": question_total,
        "question_matches": question_matches,
        "question_agreement": question_agreement,
        "question_agreement_percent": _pct(question_agreement),
        "question_no_precision": question_precision,
        "question_no_recall": question_recall,
        "question_no_f1": question_f1,
        "question_no_f1_percent": _pct(question_f1),
        "subquestion_eligible_question_count": subquestion_eligible_question_count,
        "subquestion_total": subquestion_total,
        "subquestion_matches": subquestion_matches,
        "subquestion_agreement": subquestion_agreement,
        "subquestion_agreement_percent": _pct(subquestion_agreement),
        "subquestion_precision": subquestion_precision,
        "subquestion_recall": subquestion_recall,
        "subquestion_f1": subquestion_f1,
        "subquestion_f1_percent": _pct(subquestion_f1),
        "path_exact_matches": path_exact_matches,
        "path_exact_rate": path_exact_rate,
        "path_exact_percent": _pct(path_exact_rate),
        "form_exact_match": form_exact_match,
        "question_agreements": question_agreements,
        "questions": question_details,
    }


def comparison_result_to_agreement_items(
    comparison: dict[str, Any],
    generated: AuditFormResult,
    reference: AuditFormResult,
) -> list[dict[str, Any]]:
    """Create normalized agreement rows with adjacent rationale fields."""

    items: list[dict[str, Any]] = [
        {
            "level": "overall",
            "question_id": None,
            "subquestion_id": None,
            "question_text": None,
            "subquestion_text": None,
            "generated_answer": generated.overall_outcome,
            "reference_answer": reference.overall_outcome,
            "matched": bool(comparison["outcome_match"]),
            "agreement": float(comparison["outcome_match"]),
            "generated_comment": generated.outcome_justification,
            "reference_comment": reference.outcome_justification,
            "generated_citations": None,
            "reference_citations": None,
        }
    ]

    generated_questions = _question_map(generated)
    reference_questions = _question_map(reference)
    question_ids = _ordered_question_ids(generated_questions, reference_questions, reference)

    for question_id in question_ids:
        generated_question = generated_questions.get(question_id)
        reference_question = reference_questions.get(question_id)
        generated_answer = generated_question.answer if generated_question else None
        reference_answer = reference_question.answer if reference_question else None
        question = reference_question or generated_question
        question_match = generated_answer == reference_answer
        items.append(
            {
                "level": "question",
                "question_id": question_id,
                "subquestion_id": None,
                "question_text": question.text if question else "",
                "subquestion_text": None,
                "generated_answer": _answer_text(generated_answer),
                "reference_answer": _answer_text(reference_answer),
                "matched": question_match,
                "agreement": float(question_match),
                "generated_comment": generated_question.comments if generated_question else None,
                "reference_comment": reference_question.comments if reference_question else None,
                "generated_citations": generated_question.citations if generated_question else None,
                "reference_citations": reference_question.citations if reference_question else None,
            }
        )

        if generated_answer != "No" or reference_answer != "No":
            continue

        generated_sub_questions = _sub_question_map(generated_question)
        reference_sub_questions = _sub_question_map(reference_question)
        sub_question_ids = sorted(generated_sub_questions.keys() | reference_sub_questions.keys())
        for sub_question_id in sub_question_ids:
            generated_sub_question = generated_sub_questions.get(sub_question_id)
            reference_sub_question = reference_sub_questions.get(sub_question_id)
            generated_subquestion_answer = (
                bool(generated_sub_question.answer) if generated_sub_question else False
            )
            reference_subquestion_answer = (
                bool(reference_sub_question.answer) if reference_sub_question else False
            )
            subquestion_match = generated_subquestion_answer == reference_subquestion_answer
            sub_question = reference_sub_question or generated_sub_question
            items.append(
                {
                    "level": "subquestion",
                    "question_id": question_id,
                    "subquestion_id": sub_question_id,
                    "question_text": question.text if question else "",
                    "subquestion_text": sub_question.text if sub_question else "",
                    "generated_answer": _answer_text(generated_subquestion_answer),
                    "reference_answer": _answer_text(reference_subquestion_answer),
                    "matched": subquestion_match,
                    "agreement": float(subquestion_match),
                    "generated_comment": generated_sub_question.reasoning
                    if generated_sub_question
                    else None,
                    "reference_comment": reference_sub_question.reasoning
                    if reference_sub_question
                    else None,
                    "generated_citations": generated_sub_question.citations
                    if generated_sub_question
                    else None,
                    "reference_citations": reference_sub_question.citations
                    if reference_sub_question
                    else None,
                }
            )

    return items


def comparison_result_to_row(
    comparison: dict[str, Any],
    generated: AuditFormResult,
    reference_stage: str,
    *,
    effective_date: str | None = None,
    reference_reviewer: str | None = None,
) -> dict[str, Any]:
    """Flatten a comparison result into a single exportable evaluation row."""

    row = {
        "id": generated.id,
        "ground_truth": generated.ground_truth,
        "reference_stage": reference_stage,
        "reference_reviewer": reference_reviewer,
        "effective_date": effective_date,
        "generated_outcome": comparison["generated_outcome"],
        "reference_outcome": comparison["reference_outcome"],
        "overall_outcome_agreement": float(comparison["outcome_match"]),
        "question_agreement": comparison["question_agreement"],
        "subquestion_agreement": comparison["subquestion_agreement"],
        "path_exact_match_rate": comparison["path_exact_rate"],
        "score": comparison["score"],
        "question_total": comparison["question_total"],
        "question_matches": comparison["question_matches"],
        "subquestion_eligible_question_count": comparison["subquestion_eligible_question_count"],
        "subquestion_total": comparison["subquestion_total"],
        "subquestion_matches": comparison["subquestion_matches"],
        "path_exact_matches": comparison["path_exact_matches"],
        "form_exact_match": float(comparison["form_exact_match"]),
        "generated_outcome_justification": comparison["generated_outcome_justification"],
        "reference_outcome_justification": comparison["reference_outcome_justification"],
        "details": json.dumps(comparison["questions"], ensure_ascii=True),
        "cost": generated.cost,
        "image_cost": generated.image_cost,
        "latency": generated.latency,
    }

    row.update(
        {
            f"{question_id}_agreement": agreement
            for question_id, agreement in sorted(comparison["question_agreements"].items())
        }
    )

    return row


def comparison_metrics_to_row(
    comparison: dict[str, Any],
    reference_stage: str,
) -> dict[str, Any]:
    """Flatten stored comparison metrics for aggregate recomputation."""

    row = {
        "reference_stage": reference_stage,
        "overall_outcome_agreement": float(bool(comparison.get("outcome_match"))),
        "question_agreement": float(comparison.get("question_agreement") or 0.0),
        "subquestion_agreement": float(comparison.get("subquestion_agreement") or 0.0),
        "path_exact_match_rate": float(comparison.get("path_exact_rate") or 0.0),
        "score": float(comparison.get("score") or 0.0),
        "question_total": int(comparison.get("question_total") or 0),
        "question_matches": int(comparison.get("question_matches") or 0),
        "subquestion_eligible_question_count": int(
            comparison.get("subquestion_eligible_question_count") or 0
        ),
        "subquestion_total": int(comparison.get("subquestion_total") or 0),
        "subquestion_matches": int(comparison.get("subquestion_matches") or 0),
        "path_exact_matches": int(comparison.get("path_exact_matches") or 0),
        "form_exact_match": float(bool(comparison.get("form_exact_match"))),
    }
    row.update(
        {
            f"{question_id}_agreement": float(agreement)
            for question_id, agreement in sorted(
                (comparison.get("question_agreements") or {}).items()
            )
        }
    )
    return row


def _safe_float(value: Any) -> float:
    if value is None:
        return 0.0
    value = float(value)
    return 0.0 if math.isnan(value) else value


def _sum_column(frame: pd.DataFrame, column: str) -> int:
    if column not in frame:
        return 0
    return int(frame[column].fillna(0).sum())


def _mean_column(frame: pd.DataFrame, column: str) -> float:
    if column not in frame or frame.empty:
        return 0.0
    return _safe_float(frame[column].mean())


def _add_stage_metrics(
    metrics: dict[str, float],
    prefix: str,
    stage_df: pd.DataFrame,
    question_agreement_columns: list[str],
) -> None:
    eligible_stage_df = stage_df[stage_df["subquestion_total"] > 0]
    eligible_question_count = _sum_column(stage_df, "subquestion_eligible_question_count")

    metrics[f"{prefix}_overall_outcome_agreement"] = _ratio(
        _sum_column(stage_df, "overall_outcome_agreement"),
        len(stage_df),
    )
    metrics[f"{prefix}_question_agreement"] = _ratio(
        _sum_column(stage_df, "question_matches"),
        _sum_column(stage_df, "question_total"),
    )
    metrics[f"{prefix}_subquestion_agreement"] = _ratio(
        _sum_column(stage_df, "subquestion_matches"),
        _sum_column(stage_df, "subquestion_total"),
    )
    metrics[f"{prefix}_subquestion_eligible_question_count"] = float(eligible_question_count)
    metrics[f"{prefix}_path_exact_match_rate"] = _ratio(
        _sum_column(stage_df, "path_exact_matches"),
        _sum_column(stage_df, "question_total"),
    )

    metrics[f"{prefix}_overall_outcome_agreement_macro"] = _mean_column(
        stage_df, "overall_outcome_agreement"
    )
    metrics[f"{prefix}_question_agreement_macro"] = _mean_column(stage_df, "question_agreement")
    metrics[f"{prefix}_subquestion_agreement_macro"] = (
        _mean_column(eligible_stage_df, "subquestion_agreement")
        if not eligible_stage_df.empty
        else 0.0
    )
    metrics[f"{prefix}_path_exact_match_rate_macro"] = _mean_column(
        stage_df, "path_exact_match_rate"
    )

    for question_agreement_column in question_agreement_columns:
        metrics[f"{prefix}_{question_agreement_column}"] = _mean_column(
            stage_df, question_agreement_column
        )


def aggregate_comparison_metrics(result_df: pd.DataFrame) -> dict[str, float]:
    """Aggregate evaluation metrics overall and by review stage.

    The default metrics are micro-averaged from raw counts. Matching ``_macro``
    metrics are also included for claim-level average score reporting.
    """

    metrics: dict[str, float] = {}

    if result_df.empty:
        return metrics

    aggregate_agreement_columns = {
        "overall_outcome_agreement",
        "question_agreement",
        "subquestion_agreement",
    }
    question_agreement_columns = sorted(
        column
        for column in result_df.columns
        if column.endswith("_agreement") and column not in aggregate_agreement_columns
    )

    _add_stage_metrics(metrics, "overall", result_df, question_agreement_columns)

    if "reference_stage" not in result_df:
        return metrics

    for review_stage in ("R1", "R2"):
        stage_df = result_df[result_df["reference_stage"] == review_stage]
        if stage_df.empty:
            continue
        _add_stage_metrics(metrics, review_stage, stage_df, question_agreement_columns)

    return metrics
