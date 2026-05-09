"""Audit form contracts for Targeted File Review.

The exact questionnaire variants will evolve, but agent outputs should keep this
question/sub-question/outcome shape so storage, review, and evaluation workflows
can remain stable.
"""

import json
import os
from pathlib import Path
from typing import Literal, Self

from pydantic import BaseModel, Field, model_validator
from pydantic.json_schema import SkipJsonSchema


class FormSubQuestion(BaseModel):
    id: str = Field(..., description="Stable identifier, e.g. Q1.1 or Q2.3.")
    text: str = Field(..., description="Canonical sub-question text from the form template.")
    reasoning: str = Field(
        default="",
        description="Reasoning for why this driver/sub-question applies.",
    )
    citations: str = Field(default="", description="Specific evidence citations.")
    answer: SkipJsonSchema[bool] = False
    help_text: SkipJsonSchema[str | None] = None


class FormQuestion(BaseModel):
    id: str = Field(..., description="Stable identifier, e.g. Q1 or Q2.")
    text: str = Field(..., description="Canonical question text from the form template.")
    answer: Literal["Yes", "No", "Insufficient information"] = Field(
        ..., description="Question answer."
    )
    sub_questions: list[FormSubQuestion] = Field(
        default_factory=list,
        description="Applicable sub-questions when the answer identifies an opportunity.",
    )
    missing_info: str | None = Field(
        None,
        description="Required when the answer is 'Insufficient information'.",
    )
    help_text: SkipJsonSchema[str | None] = None

    @model_validator(mode="after")
    def validate_sub_questions(self) -> Self:
        if self.answer == "No" and not self.sub_questions:
            raise ValueError("Questions marked 'No' must include at least one sub-question.")
        return self

    @model_validator(mode="after")
    def validate_missing_info(self) -> Self:
        if self.answer == "Insufficient information" and not (self.missing_info or "").strip():
            raise ValueError(
                "Questions marked 'Insufficient information' must specify missing_info."
            )
        return self


class PerilDetermination(BaseModel):
    peril: str = Field(..., description="Specific peril for the file review.")
    notes: str | None = Field(None, description="Optional peril reasoning or caveats.")


class AuditFormResult(BaseModel):
    form_id: str = Field(..., description="Registered canonical form identifier.")
    form_version: str = Field(..., description="Canonical form version completed by the agent.")
    title: str = Field(..., description="Human-friendly form title.")
    peril: PerilDetermination
    questions: list[FormQuestion]
    overall_outcome: Literal["Meets", "Does Not Meet"]
    outcome_justification: str
    id: SkipJsonSchema[str | None] = None
    cost: SkipJsonSchema[float | None] = None
    image_cost: SkipJsonSchema[float | None] = None
    latency: SkipJsonSchema[float | None] = None
    ground_truth: SkipJsonSchema[str | None] = None
    extras: SkipJsonSchema[dict[str, str] | None] = None

    def __str__(self) -> str:
        lines = [
            f"# {self.title}",
            "",
            "## Peril",
            f"- {self.peril.peril}",
        ]
        if self.peril.notes:
            lines.append(f"- Notes: {self.peril.notes}")

        lines.extend(["", "## Questions"])
        for question in self.questions:
            lines.extend([f"### {question.id} - {question.answer}", question.text])
            if question.help_text:
                lines.append(f"- Help text: {question.help_text}")
            if question.missing_info:
                lines.append(f"- Missing info: {question.missing_info}")
            for sub_question in question.sub_questions:
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

    @property
    def has_insufficient_info(self) -> bool:
        return any(question.answer == "Insufficient information" for question in self.questions)

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
            "Complete each question from the file evidence. For 'No' answers, select at least "
            "one applicable sub-question. Use 'Insufficient information' only when required "
            "evidence is truly unavailable.",
        ]
        for question in self.questions:
            help_text = f" (help_text: {question.help_text})" if question.help_text else ""
            output.append(f"\n{question.id}: {question.text}{help_text}")
            if question.sub_questions:
                output.append("Sub-Questions:")
                for sub_question in question.sub_questions:
                    sub_help = (
                        f" (help_text: {sub_question.help_text})"
                        if sub_question.help_text
                        else ""
                    )
                    output.append(f"  {sub_question.id}: {sub_question.text}{sub_help}")

        output.append("\nOverall Outcome: Options: Meets, Does Not Meet")
        return "\n".join(output)


TFRAnalysisResult = AuditFormResult

