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
    answer: bool = Field(
        default=False,
        description="True when this sub-question/driver applies to a No answer.",
    )
    help_text: SkipJsonSchema[str | None] = None


class FormQuestion(BaseModel):
    id: str = Field(..., description="Stable identifier, e.g. Q1 or Q2.")
    text: str = Field(..., description="Canonical question text from the form template.")
    answer: Literal["Yes", "No"] = Field(..., description="Question answer.")
    sub_questions: list[FormSubQuestion] = Field(
        default_factory=list,
        description="Applicable sub-questions when the answer identifies an opportunity.",
    )
    help_text: SkipJsonSchema[str | None] = None

    @model_validator(mode="after")
    def validate_sub_questions(self) -> Self:
        if self.answer == "No" and not self.sub_questions:
            raise ValueError("Questions marked 'No' must include at least one sub-question.")
        if self.answer == "No" and not any(
            sub_question.answer for sub_question in self.sub_questions
        ):
            raise ValueError(
                "Questions marked 'No' must include at least one applicable sub-question."
            )
        if self.answer == "Yes" and self.sub_questions:
            raise ValueError("Questions marked 'Yes' must not include sub-questions.")
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
            "'No'. For 'Yes' answers, return an empty sub_questions list. For 'No' answers, "
            "include at least one listed sub-question and set answer=true for every applicable "
            "driver.",
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

        output.append("\nOverall Outcome: Options: Meets, Does Not Meet")
        return "\n".join(output)


TFRAnalysisResult = AuditFormResult
