from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.models.audit import AuditFormWithFinancialsResult, AuditResult
from app.schemas.datasets import (
    CanonicalDatasetCandidate,
    DatasetReference,
    DatasetSourceRecord,
)
from app.services.catalog import FormCatalog


@dataclass(frozen=True, slots=True)
class DatasetSourceDefinition:
    id: str
    label: str
    kind: str
    description: str
    params_schema: dict[str, Any]


EXAMPLE_CODE_OWNED_SOURCE = DatasetSourceDefinition(
    id="example_code_owned_query",
    label="Example Code-Owned Query",
    kind="external_named_query",
    description=(
        "Template source for developer-written SQL/Python helpers that return "
        "CanonicalDatasetCandidate rows."
    ),
    params_schema={
        "type": "object",
        "properties": {
            "count": {
                "type": "integer",
                "minimum": 1,
                "maximum": 100,
                "default": 12,
            }
        },
    },
)

CODE_OWNED_SOURCES = (EXAMPLE_CODE_OWNED_SOURCE,)


def list_for_form(
    catalog: FormCatalog,
    form_id: str,
    form_version: str,
) -> list[DatasetSourceRecord]:
    catalog.get_form(form_id, form_version)
    return [
        DatasetSourceRecord(
            id=source.id,
            label=source.label,
            kind=source.kind,  # type: ignore[arg-type]
            form_id=form_id,
            form_versions=[form_version],
            description=source.description,
            params_schema=source.params_schema,
        )
        for source in CODE_OWNED_SOURCES
    ]


def fetch_source_candidates(
    source_id: str,
    *,
    catalog: FormCatalog,
    form_id: str,
    form_version: str,
    params: dict[str, Any] | None = None,
) -> list[CanonicalDatasetCandidate]:
    if source_id == EXAMPLE_CODE_OWNED_SOURCE.id:
        return fetch_from_example_code_owned_query(
            catalog=catalog,
            form_id=form_id,
            form_version=form_version,
            params=params or {},
        )
    raise KeyError(f"Unknown dataset source: {source_id}")


def fetch_from_example_code_owned_query(
    *,
    catalog: FormCatalog,
    form_id: str,
    form_version: str,
    params: dict[str, Any],
) -> list[CanonicalDatasetCandidate]:
    """Template fetcher for developer-owned SQL/Python dataset sources.

    Replace the generated rows below with a query/helper call, then map each returned row into
    CanonicalDatasetCandidate. Keep source_record_id stable across preview and add.
    """

    definition = catalog.get_form(form_id, form_version)
    count = int(params.get("count") or 12)
    count = max(1, min(count, 100))
    return [
        _example_candidate(definition.canonical, index, EXAMPLE_CODE_OWNED_SOURCE)
        for index in range(1, count + 1)
    ]


def _example_candidate(
    canonical: AuditResult,
    index: int,
    source: DatasetSourceDefinition,
) -> CanonicalDatasetCandidate:
    failing = index % 3 == 0 or index % 5 == 0
    result = _example_result(canonical, index, failing)
    note = (
        f"Example code-owned case {index}: "
        f"{'exception evidence present' if failing else 'support appears complete'}."
    )
    return CanonicalDatasetCandidate(
        source_key=source.id,
        source_kind=source.kind,
        source_label=source.label,
        source_record_id=f"{canonical.form_id}:{canonical.form_version}:example:{index:03d}",
        claim_number=f"EXT-{canonical.form_id.upper()}-{index:03d}",
        effective_date="2026-05-31",
        instructions=f"Review the code-owned source packet. {note}",
        input={
            "prompt": note,
            "external_source": source.id,
            "placeholder": True,
        },
        references=[
            DatasetReference(
                reference_kind="R2",
                result=result,
                reviewer="code-owned-source-example",
                source_metadata={"placeholder": True, "row_index": index},
            )
        ],
        metadata={
            "external_query_id": source.id,
            "external_record_id": f"example-{index:03d}",
            "placeholder": True,
        },
        tags=["example", "code-owned"],
    )


def _example_result(canonical: AuditResult, index: int, failing: bool) -> AuditResult:
    if isinstance(canonical, AuditFormWithFinancialsResult):
        questions = []
        for question_index, question in enumerate(canonical.questions, start=1):
            overwrite = float(index * 37) if failing and question_index == 1 else 0
            underwrite = float(index * 19) if failing and question_index == 2 else 0
            questions.append(
                question.model_copy(
                    update={
                        "answer": "No" if overwrite or underwrite else "Yes",
                        "comments": (
                            "Example source financial exception."
                            if overwrite or underwrite
                            else "Example source found no financial exception."
                        ),
                        "citations": "Example code-owned source row.",
                        "overwrite_dollars": overwrite,
                        "underwrite_dollars": underwrite,
                    }
                )
            )
        return canonical.model_copy(
            deep=True,
            update={
                "total_amount_reviewed_dollars": max(1, index * 1000),
                "questions": questions,
                "overall_outcome": "Does Not Meet" if failing else "Meets",
                "outcome_justification": (
                    "Example source case has financial exceptions."
                    if failing
                    else "Example source case has no financial exceptions."
                ),
            },
        )

    questions = []
    for question_index, question in enumerate(canonical.questions, start=1):
        sub_questions = []
        for sub_index, sub_question in enumerate(question.sub_questions or [], start=1):
            applies = failing and question_index == 1 and sub_index == 1
            sub_questions.append(
                sub_question.model_copy(
                    update={
                        "answer": applies,
                        "reasoning": (
                            "Example code-owned source evidence activates this driver."
                            if applies
                            else ""
                        ),
                        "citations": "Example code-owned source row." if applies else "",
                    }
                )
            )
        has_driver = any(sub_question.answer for sub_question in sub_questions)
        is_no = failing and (question_index == 1 or not sub_questions)
        questions.append(
            question.model_copy(
                update={
                    "answer": "No" if is_no or has_driver else "Yes",
                    "comments": (
                        "Example source exception evidence found."
                        if is_no and not sub_questions
                        else "Example source evidence supports the answer."
                    ),
                    "citations": "Example code-owned source row.",
                    "sub_questions": sub_questions,
                }
            )
        )
    return canonical.model_copy(
        deep=True,
        update={
            "questions": questions,
            "overall_outcome": "Does Not Meet" if failing else "Meets",
            "outcome_justification": (
                "Example source case contains exception evidence."
                if failing
                else "Example source case satisfies the audit form."
            ),
        },
    )
