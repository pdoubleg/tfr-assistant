"""Audit form contracts for Targeted File Review.

The exact questionnaire variants will evolve, but agent outputs should keep this
question/sub-question/outcome shape so storage, review, and evaluation workflows
can remain stable.
"""

import json
import os
from pathlib import Path
from typing import Any, Literal, Self

from pydantic import BaseModel, Field, ValidationInfo, model_validator
from pydantic.json_schema import SkipJsonSchema


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
        if _canonical_merge_context(info.context) is None:
            return self
        if self.answer and not self.reasoning.strip():
            raise ValueError("Selected sub-questions must include reasoning.")
        if self.answer and not self.citations.strip():
            raise ValueError("Selected sub-questions must include citations.")
        return self


class FormQuestion(BaseModel):
    id: str = Field(..., description="Stable identifier, e.g. Q1 or Q2.")
    text: str = Field(..., description="Canonical question text from the form template.")
    answer: Literal["Yes", "No"] = Field(..., description="Question answer.")
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
        if _canonical_merge_context(info.context) is None:
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


class AuditFormResult(BaseModel):
    form_id: str = Field(..., description="Registered canonical form identifier.")
    form_version: str = Field(..., description="Canonical form version completed by the agent.")
    title: str = Field(..., description="Human-friendly form title.")
    description: str = Field(..., description="Brief description of the completed audit form.")
    questions: list[FormQuestion]
    overall_outcome: Literal["Meets", "Does Not Meet"]
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
        canonical_context = _canonical_merge_context(info.context)
        if canonical_context is None:
            return data
        definition = getattr(canonical_context, "form_definition", None)
        return merge_payload_with_canonical(
            data,
            canonical_context.canonical,
            form_id=getattr(definition, "id", None),
            form_version=getattr(definition, "version", None),
            title=getattr(definition, "title", None),
            description=canonical_context.canonical.description,
        )

    def __str__(self) -> str:
        lines = [
            f"# {self.title}",
            "",
            "## Description",
            self.description,
        ]

        lines.extend(["", "## Questions"])
        for question in self.questions:
            lines.extend([f"### {question.id} - {question.answer}", question.text])
            if question.help_text:
                lines.append(f"- Help text: {question.help_text}")
            if question.comments:
                lines.append(f"- Comments: {question.comments}")
            if question.citations:
                lines.append(f"- Citations: {question.citations}")
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
                f"- {self.overall_outcome}",
                f"- Justification: {self.outcome_justification}",
            ]
        )
        return "\n".join(lines).strip()

    def to_json(self, path: str | Path) -> None:
        destination = Path(path)
        with destination.open("w", encoding="utf-8") as file_obj:
            json.dump(self.model_dump(), file_obj, indent=2)
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


def _has_text(value: str | None) -> bool:
    return bool((value or "").strip())


def _canonical_merge_context(context: Any) -> Any | None:
    canonical = getattr(context, "canonical", None)
    if isinstance(canonical, AuditFormResult):
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
    answer: Literal["Yes", "No"],
) -> bool:
    if answer == "Yes":
        return _has_driver_evidence(sub_question)
    return _mapping_value(sub_question, "answer", True) is not False or _has_driver_evidence(
        sub_question
    )


def merge_payload_with_canonical(
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
    """Merge a sparse generated payload with a complete canonical form.

    The LLM only needs to return applicable sub-question drivers. This helper
    restores every canonical driver, marks omitted drivers as not applicable, and
    raises ValueError with retry-friendly messages when the payload contradicts
    the canonical form.
    """

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
                and _is_applicable_driver_payload(
                    sub_question,
                    answer=answer,
                )
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
            "form_id": form_id or canonical.form_id,
            "form_version": form_version or canonical.form_version,
            "title": title or canonical.title,
            "description": description or canonical.description,
            "questions": merged_questions,
        }
    )
    return payload


def merge_with_canonical(
    generated: AuditFormResult,
    canonical: AuditFormResult,
    *,
    form_id: str | None = None,
    form_version: str | None = None,
    title: str | None = None,
    description: str | None = None,
    require_citations: bool = True,
    require_yes_question_evidence: bool = True,
) -> AuditFormResult:
    """Merge sparse generated audit answers with a complete canonical form."""

    payload = merge_payload_with_canonical(
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


TFRAnalysisResult = AuditFormResult
