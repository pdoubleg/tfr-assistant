"""Audit form contracts for Targeted File Review."""

from __future__ import annotations

import json
import os
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path
from typing import Annotated, Any, Literal, Self, TypeAlias

from pydantic import (
    BaseModel,
    Field,
    TypeAdapter,
    ValidationInfo,
    field_serializer,
    field_validator,
    model_validator,
)
from pydantic.json_schema import SkipJsonSchema

FormKind = Literal["standard", "financial"]
QuestionAnswer = Literal["Yes", "No"]
OverallOutcome = Literal["Meets", "Does Not Meet"]

MONEY_ZERO = Decimal("0.00")
MONEY_QUANT = Decimal("0.01")


def _money(value: Any, *, field_name: str = "amount") -> Decimal:
    if value is None or value == "":
        return MONEY_ZERO
    try:
        decimal_value = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{field_name} must be a valid dollar amount.") from exc
    if decimal_value < MONEY_ZERO:
        raise ValueError(f"{field_name} cannot be negative.")
    return decimal_value.quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)


def _money_json(value: Decimal | None) -> float | None:
    if value is None:
        return None
    return float(value)


def _pct_decimal(numerator: Decimal, denominator: Decimal) -> Decimal:
    if denominator <= MONEY_ZERO:
        return MONEY_ZERO
    return ((numerator / denominator) * Decimal("100")).quantize(
        MONEY_QUANT,
        rounding=ROUND_HALF_UP,
    )


class FormSubQuestion(BaseModel):
    id: str = Field(..., description="Stable identifier, e.g. Q1.1 or Q2.3.")
    text: str = Field(..., description="Canonical sub-question text from the form template.")
    reasoning: str = Field(
        default="",
        description=(
            "Reasoning for why this driver/sub-question applies. Required for every "
            "sub_question you include in generated output."
        ),
    )
    citations: str = Field(
        default="",
        description=(
            "Specific evidence citations. Required for every sub_question you include "
            "in generated output."
        ),
    )
    answer: SkipJsonSchema[bool] = True
    help_text: SkipJsonSchema[str | None] = None

    @model_validator(mode="after")
    def validate_selected_evidence(self, info: ValidationInfo) -> Self:
        if _standard_merge_context(info.context) is None:
            return self
        if self.answer and not self.reasoning.strip():
            raise ValueError("Selected sub-questions must include reasoning.")
        if self.answer and not self.citations.strip():
            raise ValueError("Selected sub-questions must include citations.")
        return self


class FormQuestion(BaseModel):
    id: str = Field(..., description="Stable identifier, e.g. Q1 or Q2.")
    text: str = Field(..., description="Canonical question text from the form template.")
    answer: QuestionAnswer = Field(..., description="Question answer.")
    comments: str | None = Field(
        default=None,
        description=(
            "Question-level reasoning/comments. Required with citations for canonical "
            "questions that do not have sub_questions. Prefer null when the questionnaire "
            "lists sub_questions because sub-question reasoning is more specific."
        ),
    )
    citations: str | None = Field(
        default=None,
        description=(
            "Question-level evidence citations. Required with comments for canonical "
            "questions that do not have sub_questions. Prefer null when the questionnaire "
            "lists sub_questions."
        ),
    )
    sub_questions: list[FormSubQuestion] | None = Field(
        default=None,
        description=(
            "Optional sparse list of applicable sub-question drivers. When the questionnaire "
            "lists sub_questions for this question, include only the listed driver(s) that "
            "apply to the audit finding; do not include non-applicable drivers. Including a "
            "sub_question means it applies, so provide reasoning and citations on it. For "
            "Yes answers where no driver applies, omit sub_questions or set it to null/[]. "
            "When the questionnaire does not list sub_questions, omit this field or set it "
            "to null/[] and put reasoning in comments and evidence references in citations."
        ),
    )
    help_text: SkipJsonSchema[str | None] = None

    @model_validator(mode="after")
    def validate_sub_questions(self, info: ValidationInfo) -> Self:
        if _standard_merge_context(info.context) is None:
            return self
        sub_questions = self.sub_questions or []
        if (
            self.answer == "No"
            and sub_questions
            and not any(sub_question.answer for sub_question in sub_questions)
        ):
            raise ValueError("No answers with sub_questions must include an applicable driver.")
        if (
            self.answer == "Yes"
            and sub_questions
            and any(sub_question.answer for sub_question in sub_questions)
        ):
            raise ValueError("Yes answers with sub_questions cannot include applicable drivers.")
        if not sub_questions:
            if not (self.comments or "").strip():
                raise ValueError("Questions without sub_questions must include comments.")
            if not (self.citations or "").strip():
                raise ValueError("Questions without sub_questions must include citations.")
        return self


class FinancialQuestionResult(BaseModel):
    id: str = Field(..., description="Stable canonical question identifier.")
    text: str = Field(..., description="Canonical financial audit question text.")
    answer: QuestionAnswer = Field(..., description="Question answer.")
    comments: str | None = Field(default=None, description="Optional question-level comments.")
    citations: str | None = Field(default=None, description="Optional evidence citations.")
    overwrite_dollars: Decimal = Field(
        default=MONEY_ZERO,
        description="Overwrite dollars for this question. Use 0 when none apply.",
    )
    underwrite_dollars: Decimal = Field(
        default=MONEY_ZERO,
        description="Underwrite dollars for this question. Use 0 when none apply.",
    )
    help_text: SkipJsonSchema[str | None] = None

    @field_validator("overwrite_dollars", "underwrite_dollars", mode="before")
    @classmethod
    def validate_money(cls, value: Any, info: ValidationInfo) -> Decimal:
        return _money(value, field_name=info.field_name or "amount")

    @field_serializer("overwrite_dollars", "underwrite_dollars")
    def serialize_money(self, value: Decimal) -> float:
        return float(value)


class AuditFormResult(BaseModel):
    form_kind: Literal["standard"] = Field(default="standard", description="Audit form kind.")
    form_id: str = Field(..., description="Registered canonical form identifier.")
    form_version: str = Field(..., description="Canonical form version completed by the agent.")
    title: str = Field(..., description="Human-friendly form title.")
    description: str = Field(..., description="Brief description of the completed audit form.")
    questions: list[FormQuestion]
    overall_outcome: OverallOutcome
    outcome_justification: str
    id: SkipJsonSchema[str | None] = None
    cost: SkipJsonSchema[float | None] = None
    image_cost: SkipJsonSchema[float | None] = None
    latency: SkipJsonSchema[float | None] = None
    ground_truth: SkipJsonSchema[str | None] = None
    extras: SkipJsonSchema[dict[str, str] | None] = None

    @model_validator(mode="before")
    @classmethod
    def validate_and_merge_with_canonical(cls, data: Any, info: ValidationInfo) -> Any:
        canonical_context = _standard_merge_context(info.context)
        if canonical_context is None:
            return data
        definition = getattr(canonical_context, "form_definition", None)
        return merge_standard_payload_with_canonical(
            data,
            canonical_context.canonical,
            form_id=getattr(definition, "id", None),
            form_version=getattr(definition, "version", None),
            title=getattr(definition, "title", None),
            description=canonical_context.canonical.description,
        )

    def __str__(self) -> str:
        return render_audit_result(self)

    def to_json(self, path: str | Path) -> None:
        destination = Path(path)
        with destination.open("w", encoding="utf-8") as file_obj:
            json.dump(self.model_dump(mode="json"), file_obj, indent=2)
            file_obj.flush()
            os.fsync(file_obj.fileno())

    @classmethod
    def from_json(cls, path: str | Path) -> Self:
        source = Path(path)
        if not source.exists():
            raise FileNotFoundError(f"JSON file not found: {source}")
        try:
            return cls.model_validate_json(source.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON format in file {source}: {exc}") from exc

    def as_questionnaire_string(self) -> str:
        output = [
            f"TFR Questionnaire: {self.title}",
            "Form Kind: standard",
            "Complete each question from the file evidence. Answers must be exactly 'Yes' or "
            "'No'. When a question lists Sub-Questions, generate only the listed "
            "sub_question driver(s) that apply to the audit finding; do not generate "
            "non-applicable drivers. Do not include an answer field on sub_questions; "
            "including a sub_question means it applies. For a No answer with listed "
            "Sub-Questions, include at least one applicable sub_question with reasoning "
            "and citations. For a Yes answer with listed Sub-Questions, omit sub_questions "
            "or set it to null/[]. Keep question-level comments/citations null unless "
            "extra general context is needed. When a question does not list Sub-Questions, "
            "omit sub_questions or set it to null/[], and put the question-level reasoning "
            "in comments and the supporting evidence references in citations.",
        ]
        for question in self.questions:
            help_text = f" (help_text: {question.help_text})" if question.help_text else ""
            output.append(f"\n{question.id}: {question.text}{help_text}")
            if question.sub_questions:
                output.append("Sub-Questions:")
                for sub_question in question.sub_questions:
                    sub_help = (
                        f" (help_text: {sub_question.help_text})" if sub_question.help_text else ""
                    )
                    output.append(f"  {sub_question.id}: {sub_question.text}{sub_help}")
            else:
                output.append(
                    "No Sub-Questions: put reasoning in question.comments and evidence in "
                    "question.citations."
                )

        output.append("\nOverall Outcome: Options: Meets, Does Not Meet")
        return "\n".join(output)


class AuditFormWithFinancialsResult(BaseModel):
    form_kind: Literal["financial"] = Field(default="financial", description="Audit form kind.")
    form_id: str = Field(..., description="Registered canonical form identifier.")
    form_version: str = Field(..., description="Canonical form version completed by the agent.")
    title: str = Field(..., description="Human-friendly form title.")
    description: str = Field(..., description="Brief description of the completed audit form.")
    total_amount_reviewed_dollars: Decimal = Field(
        ...,
        description="Total dollar amount reviewed for this audit. Must be greater than zero.",
    )
    questions: list[FinancialQuestionResult]
    overall_outcome: OverallOutcome
    outcome_justification: str
    id: SkipJsonSchema[str | None] = None
    cost: SkipJsonSchema[float | None] = None
    image_cost: SkipJsonSchema[float | None] = None
    latency: SkipJsonSchema[float | None] = None
    ground_truth: SkipJsonSchema[str | None] = None
    extras: SkipJsonSchema[dict[str, str] | None] = None

    @field_validator("total_amount_reviewed_dollars", mode="before")
    @classmethod
    def validate_total_amount(cls, value: Any) -> Decimal:
        amount = _money(value, field_name="total_amount_reviewed_dollars")
        if amount <= MONEY_ZERO:
            raise ValueError("total_amount_reviewed_dollars must be greater than zero.")
        return amount

    @field_serializer("total_amount_reviewed_dollars")
    def serialize_total_amount(self, value: Decimal) -> float:
        return float(value)

    @model_validator(mode="before")
    @classmethod
    def validate_and_merge_with_canonical(cls, data: Any, info: ValidationInfo) -> Any:
        canonical_context = _financial_merge_context(info.context)
        if canonical_context is None:
            return data
        definition = getattr(canonical_context, "form_definition", None)
        return merge_financial_payload_with_canonical(
            data,
            canonical_context.canonical,
            form_id=getattr(definition, "id", None),
            form_version=getattr(definition, "version", None),
            title=getattr(definition, "title", None),
            description=canonical_context.canonical.description,
        )

    @property
    def total_overwrite_dollars(self) -> Decimal:
        return sum((question.overwrite_dollars for question in self.questions), MONEY_ZERO)

    @property
    def total_underwrite_dollars(self) -> Decimal:
        return sum((question.underwrite_dollars for question in self.questions), MONEY_ZERO)

    @property
    def overwrite_percent(self) -> Decimal:
        return _pct_decimal(self.total_overwrite_dollars, self.total_amount_reviewed_dollars)

    @property
    def underwrite_percent(self) -> Decimal:
        return _pct_decimal(self.total_underwrite_dollars, self.total_amount_reviewed_dollars)

    def __str__(self) -> str:
        return render_audit_result(self)

    def as_questionnaire_string(self) -> str:
        output = [
            f"TFR Questionnaire: {self.title}",
            "Form Kind: financial",
            "Complete each question from the file evidence. Answers must be exactly 'Yes' or "
            "'No'. Include total_amount_reviewed_dollars for the full reviewed amount. "
            "For each question, include overwrite_dollars and underwrite_dollars when a "
            "financial exception applies; use 0 when none apply. Keep the canonical question "
            "text in your output.",
        ]
        for question in self.questions:
            help_text = f" (help_text: {question.help_text})" if question.help_text else ""
            output.append(f"\n{question.id}: {question.text}{help_text}")
        output.append("\nOverall Outcome: Options: Meets, Does Not Meet")
        return "\n".join(output)


AuditResult: TypeAlias = Annotated[  # noqa: UP040
    AuditFormResult | AuditFormWithFinancialsResult,
    Field(discriminator="form_kind"),
]
AuditResultAdapter = TypeAdapter(AuditResult)


def parse_audit_result(payload: Any) -> AuditFormResult | AuditFormWithFinancialsResult:
    if isinstance(payload, AuditFormResult | AuditFormWithFinancialsResult):
        return payload
    if isinstance(payload, dict) and not payload.get("form_kind"):
        payload = {**payload, "form_kind": "standard"}
    return AuditResultAdapter.validate_python(payload)


def audit_result_payload(result: AuditFormResult | AuditFormWithFinancialsResult) -> dict[str, Any]:
    return result.model_dump(mode="json")


def audit_result_form_kind(result: AuditFormResult | AuditFormWithFinancialsResult) -> str:
    return result.form_kind


def financial_totals(result: AuditFormResult | AuditFormWithFinancialsResult) -> dict[str, Decimal]:
    if isinstance(result, AuditFormWithFinancialsResult):
        return {
            "total_amount_reviewed_dollars": result.total_amount_reviewed_dollars,
            "total_overwrite_dollars": result.total_overwrite_dollars,
            "total_underwrite_dollars": result.total_underwrite_dollars,
            "overwrite_percent": result.overwrite_percent,
            "underwrite_percent": result.underwrite_percent,
        }
    return {
        "total_amount_reviewed_dollars": MONEY_ZERO,
        "total_overwrite_dollars": MONEY_ZERO,
        "total_underwrite_dollars": MONEY_ZERO,
        "overwrite_percent": MONEY_ZERO,
        "underwrite_percent": MONEY_ZERO,
    }


def render_audit_result(result: AuditFormResult | AuditFormWithFinancialsResult) -> str:
    lines = [
        f"# {result.title}",
        "",
        f"- Form: {result.form_id}@{result.form_version}",
        f"- Form Kind: {result.form_kind}",
        "",
        "## Description",
        result.description,
    ]

    if isinstance(result, AuditFormWithFinancialsResult):
        lines.extend(
            [
                "",
                "## Financial Totals",
                f"- Total Amount Reviewed: ${result.total_amount_reviewed_dollars:,.2f}",
                f"- Overwrite Total: ${result.total_overwrite_dollars:,.2f}",
                f"- Underwrite Total: ${result.total_underwrite_dollars:,.2f}",
                f"- Overwrite %: {result.overwrite_percent}%",
                f"- Underwrite %: {result.underwrite_percent}%",
            ]
        )

    lines.extend(["", "## Questions"])
    for question in result.questions:
        lines.extend([f"### {question.id} - {question.answer}", question.text])
        if getattr(question, "help_text", None):
            lines.append(f"- Help text: {question.help_text}")
        if question.comments:
            lines.append(f"- Comments: {question.comments}")
        if question.citations:
            lines.append(f"- Citations: {question.citations}")
        if isinstance(question, FinancialQuestionResult):
            lines.append(f"- Overwrite: ${question.overwrite_dollars:,.2f}")
            lines.append(f"- Underwrite: ${question.underwrite_dollars:,.2f}")
        else:
            for sub_question in question.sub_questions or []:
                lines.extend(
                    [
                        f"#### {sub_question.id}",
                        sub_question.text,
                        f"- Applicable: {sub_question.answer}",
                        f"- Reasoning: {sub_question.reasoning}",
                        f"- Citations: {sub_question.citations}",
                    ]
                )
        lines.append("")

    lines.extend(
        [
            "## Outcome",
            f"- {result.overall_outcome}",
            f"- Justification: {result.outcome_justification}",
        ]
    )
    return "\n".join(lines).strip()


def compact_audit_result_text(result: AuditFormResult | AuditFormWithFinancialsResult) -> str:
    lines = [
        f"{result.form_id}@{result.form_version} ({result.form_kind})",
        f"Outcome: {result.overall_outcome}",
    ]
    if isinstance(result, AuditFormWithFinancialsResult):
        lines.append(f"Total reviewed: ${result.total_amount_reviewed_dollars:,.2f}")
        lines.append(f"OW ${result.total_overwrite_dollars:,.2f} ({result.overwrite_percent}%)")
        lines.append(f"UW ${result.total_underwrite_dollars:,.2f} ({result.underwrite_percent}%)")
    for question in result.questions:
        if isinstance(question, FinancialQuestionResult):
            lines.append(
                f"{question.id}: {question.answer}; OW ${question.overwrite_dollars:,.2f}; "
                f"UW ${question.underwrite_dollars:,.2f}; {question.comments or ''}"
            )
            continue
        drivers = [
            f"{sub_question.id}={sub_question.answer}"
            for sub_question in question.sub_questions or []
            if sub_question.answer
        ]
        suffix = f"; drivers: {', '.join(drivers)}" if drivers else ""
        lines.append(f"{question.id}: {question.answer}{suffix}; {question.comments or ''}")
    return "\n".join(lines)


def _has_text(value: str | None) -> bool:
    return bool((value or "").strip())


def _standard_merge_context(context: Any) -> Any | None:
    canonical = getattr(context, "canonical", None)
    if isinstance(canonical, AuditFormResult):
        return context
    return None


def _financial_merge_context(context: Any) -> Any | None:
    canonical = getattr(context, "canonical", None)
    if isinstance(canonical, AuditFormWithFinancialsResult):
        return context
    return None


def _duplicate_ids(ids: list[str]) -> list[str]:
    return sorted({item_id for item_id in ids if ids.count(item_id) > 1})


def _mapping_value(item: Any, key: str, default: Any = None) -> Any:
    if isinstance(item, dict):
        return item.get(key, default)
    return getattr(item, key, default)


def _has_driver_evidence(sub_question: Any) -> bool:
    return _has_text(_mapping_value(sub_question, "reasoning")) or _has_text(
        _mapping_value(sub_question, "citations")
    )


def _is_applicable_driver_payload(
    sub_question: Any,
    *,
    answer: QuestionAnswer,
) -> bool:
    if answer == "Yes":
        return _has_driver_evidence(sub_question)
    return _mapping_value(sub_question, "answer", True) is not False or _has_driver_evidence(
        sub_question
    )


def merge_standard_payload_with_canonical(
    generated: Any,
    canonical: AuditFormResult,
    *,
    form_id: str | None = None,
    form_version: str | None = None,
    title: str | None = None,
    description: str | None = None,
    require_citations: bool = True,
    require_yes_question_evidence: bool = True,
) -> dict[str, Any]:
    """Merge a sparse generated standard audit payload with a complete canonical form."""

    if not isinstance(generated, dict):
        return generated

    generated_question_items = generated.get("questions")
    if not isinstance(generated_question_items, list):
        return generated

    generated_question_ids = [
        question.get("id")
        for question in generated_question_items
        if isinstance(question, dict) and isinstance(question.get("id"), str)
    ]
    canonical_question_ids = [question.id for question in canonical.questions]
    generated_questions = {
        question["id"]: question
        for question in generated_question_items
        if isinstance(question, dict) and isinstance(question.get("id"), str)
    }
    canonical_question_set = set(canonical_question_ids)
    problems: list[str] = []

    malformed_questions = len(generated_question_items) - len(generated_question_ids)
    if malformed_questions:
        problems.append(f"{malformed_questions} generated question(s) are missing string ids.")

    duplicate_questions = _duplicate_ids(generated_question_ids)
    if duplicate_questions:
        problems.append(f"Duplicate question ids: {', '.join(duplicate_questions)}.")

    missing_questions = [
        question_id
        for question_id in canonical_question_ids
        if question_id not in generated_questions
    ]
    if missing_questions:
        problems.append(f"Missing canonical questions: {', '.join(missing_questions)}.")

    extra_questions = sorted(set(generated_question_ids) - canonical_question_set)
    if extra_questions:
        problems.append(f"Unexpected question ids: {', '.join(extra_questions)}.")

    merged_questions: list[dict[str, object]] = []
    for canonical_question in canonical.questions:
        generated_question = generated_questions.get(canonical_question.id)
        if generated_question is None:
            continue
        answer = generated_question.get("answer")
        if answer not in {"Yes", "No"}:
            problems.append(f"{canonical_question.id} answer must be exactly Yes or No.")
            continue

        canonical_sub_questions = canonical_question.sub_questions or []
        generated_sub_question_items = generated_question.get("sub_questions") or []
        if not isinstance(generated_sub_question_items, list):
            problems.append(f"{canonical_question.id} sub_questions must be a list or null.")
            generated_sub_question_items = []
        canonical_sub_ids = [sub_question.id for sub_question in canonical_sub_questions]
        canonical_sub_by_id = {
            sub_question.id: sub_question for sub_question in canonical_sub_questions
        }
        generated_sub_ids = [
            sub_question.get("id")
            for sub_question in generated_sub_question_items
            if isinstance(sub_question, dict) and isinstance(sub_question.get("id"), str)
        ]
        generated_sub_by_id = {
            sub_question["id"]: sub_question
            for sub_question in generated_sub_question_items
            if isinstance(sub_question, dict) and isinstance(sub_question.get("id"), str)
        }

        malformed_sub_questions = len(generated_sub_question_items) - len(generated_sub_ids)
        if malformed_sub_questions:
            problems.append(
                f"{canonical_question.id} has {malformed_sub_questions} sub_question(s) "
                "missing string ids."
            )

        duplicate_sub_questions = _duplicate_ids(generated_sub_ids)
        if duplicate_sub_questions:
            problems.append(
                f"{canonical_question.id} has duplicate sub_question ids: "
                f"{', '.join(duplicate_sub_questions)}."
            )

        if canonical_sub_questions:
            unknown_sub_questions = sorted(set(generated_sub_ids) - set(canonical_sub_ids))
            if unknown_sub_questions:
                problems.append(
                    f"{canonical_question.id} included non-canonical sub_question ids: "
                    f"{', '.join(unknown_sub_questions)}."
                )
            selected_sub_questions = [
                sub_question
                for sub_question in generated_sub_question_items
                if isinstance(sub_question, dict)
                and sub_question.get("id") in canonical_sub_by_id
                and _is_applicable_driver_payload(sub_question, answer=answer)
            ]
            if answer == "Yes" and selected_sub_questions:
                selected_ids = ", ".join(
                    str(sub_question.get("id")) for sub_question in selected_sub_questions
                )
                problems.append(
                    f"{canonical_question.id} answered Yes but included applicable "
                    f"sub_question evidence for: {selected_ids}."
                )
            if answer == "No" and not selected_sub_questions:
                problems.append(
                    f"{canonical_question.id} answered No and must include at least one "
                    "applicable canonical sub_question driver."
                )

            merged_sub_questions = []
            for canonical_sub_question in canonical_sub_questions:
                generated_sub_question = generated_sub_by_id.get(canonical_sub_question.id)
                if generated_sub_question is None or not _is_applicable_driver_payload(
                    generated_sub_question,
                    answer=answer,
                ):
                    merged_sub_questions.append(
                        {
                            "id": canonical_sub_question.id,
                            "text": canonical_sub_question.text,
                            "reasoning": "",
                            "citations": "",
                            "answer": False,
                            "help_text": canonical_sub_question.help_text,
                        }
                    )
                    continue

                if not _has_text(generated_sub_question.get("reasoning")):
                    problems.append(f"{canonical_sub_question.id} needs reasoning.")
                if require_citations and not _has_text(generated_sub_question.get("citations")):
                    problems.append(f"{canonical_sub_question.id} needs citations.")
                merged_sub_questions.append(
                    {
                        "id": canonical_sub_question.id,
                        "text": canonical_sub_question.text,
                        "reasoning": generated_sub_question.get("reasoning") or "",
                        "citations": generated_sub_question.get("citations") or "",
                        "answer": True,
                        "help_text": canonical_sub_question.help_text,
                    }
                )

            merged_questions.append(
                {
                    "id": canonical_question.id,
                    "text": canonical_question.text,
                    "answer": answer,
                    "comments": (
                        generated_question.get("comments")
                        if _has_text(generated_question.get("comments"))
                        else None
                    ),
                    "citations": (
                        generated_question.get("citations")
                        if _has_text(generated_question.get("citations"))
                        else None
                    ),
                    "sub_questions": merged_sub_questions,
                    "help_text": canonical_question.help_text,
                }
            )
            continue

        if generated_sub_question_items:
            problems.append(
                f"{canonical_question.id} has no canonical sub_questions; use "
                "question-level comments and citations instead."
            )
        requires_question_evidence = answer == "No" or require_yes_question_evidence
        if requires_question_evidence and not _has_text(generated_question.get("comments")):
            problems.append(f"{canonical_question.id} needs question-level comments.")
        if (
            requires_question_evidence
            and require_citations
            and not _has_text(generated_question.get("citations"))
        ):
            problems.append(f"{canonical_question.id} needs question-level citations.")

        merged_questions.append(
            {
                "id": canonical_question.id,
                "text": canonical_question.text,
                "answer": answer,
                "comments": generated_question.get("comments"),
                "citations": generated_question.get("citations"),
                "sub_questions": None,
                "help_text": canonical_question.help_text,
            }
        )

    if problems:
        raise ValueError(" ".join(problems))

    payload = dict(generated)
    payload.update(
        {
            "form_kind": "standard",
            "form_id": form_id or canonical.form_id,
            "form_version": form_version or canonical.form_version,
            "title": title or canonical.title,
            "description": description or canonical.description,
            "questions": merged_questions,
        }
    )
    return payload


def merge_financial_payload_with_canonical(
    generated: Any,
    canonical: AuditFormWithFinancialsResult,
    *,
    form_id: str | None = None,
    form_version: str | None = None,
    title: str | None = None,
    description: str | None = None,
) -> dict[str, Any]:
    """Merge a generated financial audit payload with a complete canonical form."""

    if not isinstance(generated, dict):
        return generated
    generated_question_items = generated.get("questions")
    if not isinstance(generated_question_items, list):
        return generated

    generated_question_ids = [
        question.get("id")
        for question in generated_question_items
        if isinstance(question, dict) and isinstance(question.get("id"), str)
    ]
    canonical_question_ids = [question.id for question in canonical.questions]
    generated_questions = {
        question["id"]: question
        for question in generated_question_items
        if isinstance(question, dict) and isinstance(question.get("id"), str)
    }
    problems: list[str] = []
    if len(generated_question_items) != len(generated_question_ids):
        problems.append("Every generated financial question must include a string id.")
    duplicate_questions = _duplicate_ids(generated_question_ids)
    if duplicate_questions:
        problems.append(f"Duplicate question ids: {', '.join(duplicate_questions)}.")
    missing_questions = [
        question_id
        for question_id in canonical_question_ids
        if question_id not in generated_questions
    ]
    if missing_questions:
        problems.append(f"Missing canonical questions: {', '.join(missing_questions)}.")
    extra_questions = sorted(set(generated_question_ids) - set(canonical_question_ids))
    if extra_questions:
        problems.append(f"Unexpected question ids: {', '.join(extra_questions)}.")

    merged_questions: list[dict[str, object]] = []
    for canonical_question in canonical.questions:
        generated_question = generated_questions.get(canonical_question.id)
        if generated_question is None:
            continue
        answer = generated_question.get("answer")
        if answer not in {"Yes", "No"}:
            problems.append(f"{canonical_question.id} answer must be exactly Yes or No.")
            continue
        if generated_question.get("sub_questions"):
            problems.append(
                f"{canonical_question.id} is a financial question and cannot include drivers."
            )
        try:
            overwrite = _money(
                generated_question.get("overwrite_dollars"),
                field_name=f"{canonical_question.id} overwrite_dollars",
            )
            underwrite = _money(
                generated_question.get("underwrite_dollars"),
                field_name=f"{canonical_question.id} underwrite_dollars",
            )
        except ValueError as exc:
            problems.append(str(exc))
            overwrite = MONEY_ZERO
            underwrite = MONEY_ZERO
        merged_questions.append(
            {
                "id": canonical_question.id,
                "text": canonical_question.text,
                "answer": answer,
                "comments": generated_question.get("comments"),
                "citations": generated_question.get("citations"),
                "overwrite_dollars": overwrite,
                "underwrite_dollars": underwrite,
                "help_text": canonical_question.help_text,
            }
        )

    try:
        total_amount = _money(
            generated.get("total_amount_reviewed_dollars"),
            field_name="total_amount_reviewed_dollars",
        )
        if total_amount <= MONEY_ZERO:
            problems.append("total_amount_reviewed_dollars must be greater than zero.")
    except ValueError as exc:
        problems.append(str(exc))
        total_amount = MONEY_ZERO

    if problems:
        raise ValueError(" ".join(problems))

    payload = dict(generated)
    payload.update(
        {
            "form_kind": "financial",
            "form_id": form_id or canonical.form_id,
            "form_version": form_version or canonical.form_version,
            "title": title or canonical.title,
            "description": description or canonical.description,
            "total_amount_reviewed_dollars": total_amount,
            "questions": merged_questions,
        }
    )
    return payload


def merge_with_canonical(
    generated: AuditFormResult | AuditFormWithFinancialsResult,
    canonical: AuditFormResult | AuditFormWithFinancialsResult,
    *,
    form_id: str | None = None,
    form_version: str | None = None,
    title: str | None = None,
    description: str | None = None,
    require_citations: bool = True,
    require_yes_question_evidence: bool = True,
) -> AuditFormResult | AuditFormWithFinancialsResult:
    """Merge sparse generated audit answers with a complete canonical form."""

    if isinstance(canonical, AuditFormWithFinancialsResult):
        payload = merge_financial_payload_with_canonical(
            generated.model_dump(mode="json"),
            canonical,
            form_id=form_id,
            form_version=form_version,
            title=title,
            description=description,
        )
        return AuditFormWithFinancialsResult.model_validate(payload)

    if not isinstance(generated, AuditFormResult):
        generated = AuditFormResult.model_validate(generated.model_dump(mode="json"))
    payload = merge_standard_payload_with_canonical(
        generated.model_dump(mode="json"),
        canonical,
        form_id=form_id,
        form_version=form_version,
        title=title,
        description=description,
        require_citations=require_citations,
        require_yes_question_evidence=require_yes_question_evidence,
    )
    return AuditFormResult.model_validate(payload)


# Backwards-compatible aliases used by older imports.
merge_payload_with_canonical = merge_standard_payload_with_canonical
TFRAnalysisResult = AuditResult
