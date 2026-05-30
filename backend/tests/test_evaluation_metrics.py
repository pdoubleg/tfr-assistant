import json

import pandas as pd

from app.models.audit import (
    AuditFormResult,
    AuditFormWithFinancialsResult,
    FinancialQuestionResult,
    FormQuestion,
    FormSubQuestion,
)
from app.services.evaluation_metrics import (
    aggregate_comparison_metrics,
    compare_audit_results,
    comparison_metrics_to_row,
    comparison_result_to_agreement_items,
    comparison_result_to_row,
)


def _sub_question(
    subquestion_id: str,
    *,
    answer: bool,
    reasoning: str,
    citations: str,
) -> FormSubQuestion:
    return FormSubQuestion(
        id=subquestion_id,
        text=f"{subquestion_id} text",
        answer=answer,
        reasoning=reasoning,
        citations=citations,
    )


def _question(
    question_id: str,
    *,
    answer: str,
    comments: str | None = None,
    citations: str | None = None,
    sub_questions: list[FormSubQuestion] | None = None,
) -> FormQuestion:
    return FormQuestion(
        id=question_id,
        text=f"{question_id} text",
        answer=answer,  # type: ignore[arg-type]
        comments=comments,
        citations=citations,
        sub_questions=sub_questions,
    )


def _result(
    *,
    result_id: str = "generated-1",
    q1_answer: str = "No",
    q1_sub_answers: tuple[bool, bool] = (True, False),
    q2_answer: str = "Yes",
    outcome: str = "Does Not Meet",
    outcome_justification: str = "Outcome rationale.",
) -> AuditFormResult:
    return AuditFormResult(
        id=result_id,
        form_id="tfr_default",
        form_version="v0.2",
        title="Eval test",
        description="Eval test form",
        questions=[
            _question(
                "Q1",
                answer=q1_answer,
                sub_questions=[
                    _sub_question(
                        "Q1.1",
                        answer=q1_sub_answers[0],
                        reasoning=f"Q1.1 {result_id} reasoning",
                        citations=f"Q1.1 {result_id} citations",
                    ),
                    _sub_question(
                        "Q1.2",
                        answer=q1_sub_answers[1],
                        reasoning=f"Q1.2 {result_id} reasoning",
                        citations=f"Q1.2 {result_id} citations",
                    ),
                ],
            ),
            _question(
                "Q2",
                answer=q2_answer,
                comments=f"Q2 {result_id} comments",
                citations=f"Q2 {result_id} citations",
                sub_questions=None,
            ),
        ],
        overall_outcome=outcome,  # type: ignore[arg-type]
        outcome_justification=outcome_justification,
        cost=1.2,
        image_cost=0.3,
        latency=4.5,
    )


def test_compare_audit_results_exact_match_uses_compact_details() -> None:
    generated = _result()
    reference = _result(result_id="reference-1")

    comparison = compare_audit_results(generated, reference)

    assert comparison["metric_schema_version"] == 3
    assert comparison["outcome_match"] is True
    assert comparison["question_agreement"] == 1.0
    assert comparison["subquestion_agreement"] == 1.0
    assert comparison["subquestion_eligible_question_count"] == 1
    assert comparison["path_exact_rate"] == 1.0
    assert comparison["form_exact_match"] is True
    assert comparison["questions"] == []
    assert comparison["question_agreements"] == {"Q1": 1.0, "Q2": 1.0}


def test_compare_audit_results_captures_misaligned_questions_and_subquestions() -> None:
    generated = _result(
        q1_sub_answers=(False, True),
        q2_answer="Yes",
        outcome="Meets",
        outcome_justification="Generated outcome rationale.",
    )
    reference = _result(
        result_id="reference-1",
        q1_sub_answers=(True, False),
        q2_answer="No",
        outcome="Does Not Meet",
        outcome_justification="Reference outcome rationale.",
    )

    comparison = compare_audit_results(generated, reference)

    assert comparison["outcome_match"] is False
    assert comparison["question_matches"] == 1
    assert comparison["question_total"] == 2
    assert comparison["subquestion_matches"] == 0
    assert comparison["subquestion_total"] == 2
    assert comparison["subquestion_f1"] == 0.0
    assert comparison["question_agreements"] == {"Q1": 1.0, "Q2": 0.0}

    question_details = comparison["questions"]
    assert [question["id"] for question in question_details] == ["Q1", "Q2"]
    assert [sub_question["id"] for sub_question in question_details[0]["sub_questions"]] == [
        "Q1.1",
        "Q1.2",
    ]
    assert question_details[1]["generated_answer"] == "Yes"
    assert question_details[1]["reference_answer"] == "No"


def test_agreement_items_include_answers_text_comments_reasoning_and_citations() -> None:
    generated = _result(outcome_justification="Generated outcome rationale.")
    reference = _result(result_id="reference-1", outcome_justification="Reference rationale.")
    comparison = compare_audit_results(generated, reference)

    items = comparison_result_to_agreement_items(comparison, generated, reference)

    overall = next(item for item in items if item["level"] == "overall")
    assert overall["generated_comment"] == "Generated outcome rationale."
    assert overall["reference_comment"] == "Reference rationale."
    assert overall["generated_answer"] == "Does Not Meet"

    question = next(
        item for item in items if item["level"] == "question" and item["question_id"] == "Q2"
    )
    assert question["question_text"] == "Q2 text"
    assert question["generated_comment"] == "Q2 generated-1 comments"
    assert question["reference_citations"] == "Q2 reference-1 citations"

    subquestion = next(
        item
        for item in items
        if item["level"] == "subquestion" and item["subquestion_id"] == "Q1.1"
    )
    assert subquestion["question_text"] == "Q1 text"
    assert subquestion["subquestion_text"] == "Q1.1 text"
    assert subquestion["generated_answer"] == "true"
    assert subquestion["reference_answer"] == "true"
    assert subquestion["generated_comment"] == "Q1.1 generated-1 reasoning"
    assert subquestion["reference_citations"] == "Q1.1 reference-1 citations"


def test_comparison_row_and_aggregate_metrics_use_raw_counts() -> None:
    exact_generated = _result()
    exact_reference = _result(result_id="reference-1")
    mismatch_generated = _result(q1_sub_answers=(False, True), q2_answer="Yes")
    mismatch_reference = _result(
        result_id="reference-2",
        q1_sub_answers=(True, False),
        q2_answer="No",
    )

    exact = compare_audit_results(exact_generated, exact_reference)
    mismatch = compare_audit_results(mismatch_generated, mismatch_reference)
    export_row = comparison_result_to_row(
        mismatch,
        mismatch_generated,
        "R2",
        effective_date="2026-05-01",
        reference_reviewer="reviewer-1",
    )

    assert export_row["reference_stage"] == "R2"
    assert json.loads(export_row["details"])[0]["id"] == "Q1"
    assert export_row["Q1_agreement"] == 1.0
    assert export_row["Q2_agreement"] == 0.0

    result_df = pd.DataFrame(
        [
            comparison_metrics_to_row(exact, "R1"),
            comparison_metrics_to_row(mismatch, "R1"),
            comparison_metrics_to_row(mismatch, "R2"),
        ]
    )
    metrics = aggregate_comparison_metrics(result_df)

    assert metrics["overall_question_agreement"] == 4 / 6
    assert metrics["overall_subquestion_agreement"] == 2 / 6
    assert metrics["R1_question_agreement"] == 3 / 4
    assert metrics["R1_subquestion_agreement"] == 2 / 4
    assert metrics["R2_question_agreement"] == 1 / 2
    assert metrics["R2_subquestion_agreement"] == 0.0


def _financial_question(
    question_id: str,
    *,
    answer: str = "Yes",
    overwrite: float = 0,
    underwrite: float = 0,
) -> FinancialQuestionResult:
    return FinancialQuestionResult(
        id=question_id,
        text=f"{question_id} financial text",
        answer=answer,  # type: ignore[arg-type]
        comments=f"{question_id} comments",
        citations=f"{question_id} citations",
        overwrite_dollars=overwrite,
        underwrite_dollars=underwrite,
    )


def _financial_result(
    *,
    result_id: str = "financial-1",
    total_reviewed: float = 1000,
    q1_overwrite: float = 25,
    q2_underwrite: float = 10,
    outcome: str = "Does Not Meet",
) -> AuditFormWithFinancialsResult:
    return AuditFormWithFinancialsResult(
        id=result_id,
        form_id="financial_claim_review",
        form_version="v0.1",
        title="Financial review",
        description="Financial review form",
        total_amount_reviewed_dollars=total_reviewed,
        questions=[
            _financial_question("FQ1", answer="No", overwrite=q1_overwrite),
            _financial_question("FQ2", answer="No", underwrite=q2_underwrite),
        ],
        overall_outcome=outcome,  # type: ignore[arg-type]
        outcome_justification="Financial outcome rationale.",
    )


def test_financial_compare_calculates_totals_percentages_and_items() -> None:
    generated = _financial_result(q1_overwrite=20, q2_underwrite=10)
    reference = _financial_result(result_id="financial-ref", q1_overwrite=25, q2_underwrite=15)

    comparison = compare_audit_results(generated, reference)
    items = comparison_result_to_agreement_items(comparison, generated, reference)

    assert comparison["form_kind"] == "financial"
    assert comparison["generated_total_overwrite_dollars"] == 20
    assert comparison["reference_total_overwrite_dollars"] == 25
    assert comparison["generated_overwrite_percent"] == 2
    assert comparison["reference_overwrite_percent"] == 2.5
    assert "financial_score" in comparison["applicable_metric_keys"]
    assert 0 <= comparison["financial_score"] <= 1

    question_item = next(item for item in items if item["level"] == "financial_question")
    assert question_item["generated_overwrite_dollars"] == 20
    assert question_item["reference_overwrite_dollars"] == 25
    assert question_item["overwrite_dollar_error"] == 5
