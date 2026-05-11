from typing import Any

from app.models.audit import AuditFormResult, FormQuestion


def _pct(value: float) -> float:
    return round(value * 100, 2)


def _ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def _f1(precision: float, recall: float) -> float:
    return (2 * precision * recall / (precision + recall)) if precision + recall else 0.0


def _question_map(form: AuditFormResult) -> dict[str, FormQuestion]:
    return {question.id: question for question in form.questions}


def _applicable_driver_ids(question: FormQuestion | None) -> set[str]:
    if question is None:
        return set()
    return {sub_question.id for sub_question in question.sub_questions if bool(sub_question.answer)}


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
    question_ids = [question.id for question in reference.questions]
    for question_id in generated_questions:
        if question_id not in reference_questions:
            question_ids.append(question_id)

    question_matches = 0
    question_true_positive = 0
    question_false_positive = 0
    question_false_negative = 0
    path_exact_matches = 0
    subquestion_matches = 0
    subquestion_total = 0
    driver_true_positive = 0
    driver_false_positive = 0
    driver_false_negative = 0
    question_details: list[dict[str, Any]] = []

    for question_id in question_ids:
        generated_question = generated_questions.get(question_id)
        reference_question = reference_questions.get(question_id)
        generated_answer = generated_question.answer if generated_question else None
        reference_answer = reference_question.answer if reference_question else None
        question_match = generated_answer == reference_answer
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

        generated_drivers = _applicable_driver_ids(generated_question)
        reference_drivers = _applicable_driver_ids(reference_question)
        driver_ids = sorted(generated_drivers | reference_drivers)
        driver_matches = 0
        driver_details = []
        for driver_id in driver_ids:
            generated_driver = driver_id in generated_drivers
            reference_driver = driver_id in reference_drivers
            if generated_driver == reference_driver:
                driver_matches += 1
                subquestion_matches += 1
            elif generated_driver and not reference_driver:
                driver_false_positive += 1
            elif reference_driver and not generated_driver:
                driver_false_negative += 1
            if generated_driver and reference_driver:
                driver_true_positive += 1
            subquestion_total += 1
            driver_details.append(
                {
                    "id": driver_id,
                    "generated": generated_driver,
                    "reference": reference_driver,
                    "match": generated_driver == reference_driver,
                }
            )

        path_exact = question_match and generated_drivers == reference_drivers
        if path_exact:
            path_exact_matches += 1

        question_details.append(
            {
                "id": question_id,
                "text": (reference_question or generated_question).text
                if (reference_question or generated_question)
                else "",
                "generated_answer": generated_answer,
                "reference_answer": reference_answer,
                "answer_match": question_match,
                "generated_drivers": sorted(generated_drivers),
                "reference_drivers": sorted(reference_drivers),
                "driver_match_count": driver_matches,
                "driver_total": len(driver_ids),
                "path_exact": path_exact,
                "drivers": driver_details,
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

    driver_precision = _ratio(
        driver_true_positive,
        driver_true_positive + driver_false_positive,
    )
    driver_recall = _ratio(
        driver_true_positive,
        driver_true_positive + driver_false_negative,
    )
    driver_f1 = _f1(driver_precision, driver_recall)
    form_exact_match = outcome_match and path_exact_matches == question_total

    score = (float(outcome_match) + question_agreement + path_exact_rate + driver_f1) / 4

    return {
        "score": score,
        "score_percent": _pct(score),
        "outcome_match": outcome_match,
        "outcome_score": float(outcome_match),
        "generated_outcome": generated.overall_outcome,
        "reference_outcome": reference.overall_outcome,
        "question_total": question_total,
        "question_matches": question_matches,
        "question_agreement": question_agreement,
        "question_agreement_percent": _pct(question_agreement),
        "question_no_precision": question_precision,
        "question_no_recall": question_recall,
        "question_no_f1": question_f1,
        "question_no_f1_percent": _pct(question_f1),
        "subquestion_total": subquestion_total,
        "subquestion_matches": subquestion_matches,
        "subquestion_agreement": subquestion_agreement,
        "subquestion_agreement_percent": _pct(subquestion_agreement),
        "driver_precision": driver_precision,
        "driver_recall": driver_recall,
        "driver_f1": driver_f1,
        "driver_f1_percent": _pct(driver_f1),
        "path_exact_matches": path_exact_matches,
        "path_exact_rate": path_exact_rate,
        "path_exact_percent": _pct(path_exact_rate),
        "form_exact_match": form_exact_match,
        "questions": question_details,
    }
