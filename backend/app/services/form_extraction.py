import re
from pathlib import Path

from app.models.audit import AuditFormResult, FormQuestion, FormSubQuestion


def _slug_from_filename(filename: str | None) -> str:
    stem = Path(filename or "").stem.lower()
    slug = re.sub(r"[^a-z0-9]+", "_", stem).strip("_")
    return slug or "uploaded_audit_form"


def _title_from_slug(slug: str) -> str:
    return " ".join(part.capitalize() for part in slug.split("_")) or "Uploaded Audit Form"


def extract_audit_form_from_excel(
    workbook: bytes | str | Path,
    *,
    filename: str | None = None,
) -> AuditFormResult:
    """Placeholder Excel-to-canonical extraction.

    The real extractor will parse the uploaded workbook, including xlsb inputs, and
    return a fully populated AuditFormResult. For now this function intentionally
    returns a valid template so the registration workflow can be wired end to end.
    """

    if isinstance(workbook, bytes):
        workbook_size = len(workbook)
    else:
        source = Path(workbook)
        workbook_size = source.stat().st_size if source.exists() else 0
        filename = filename or source.name

    form_id = _slug_from_filename(filename)
    title = _title_from_slug(form_id)
    description = (
        "Draft canonical form extracted from the uploaded workbook. Review and edit "
        "the generated fields before registering."
    )
    if workbook_size:
        description += f" Source workbook size: {workbook_size:,} bytes."

    return AuditFormResult(
        form_id=form_id,
        form_version="v0.1",
        title=title,
        description=description,
        questions=[
            FormQuestion(
                id="Q1",
                text="Does the file satisfy the primary audit requirement from the uploaded form?",
                answer="No",
                help_text="Placeholder question generated until workbook parsing is implemented.",
                sub_questions=[
                    FormSubQuestion(
                        id="Q1.1",
                        text="The file evidence does not satisfy the uploaded form requirement.",
                        reasoning="Placeholder extracted form driver selected for validation.",
                        citations="Uploaded workbook placeholder.",
                        answer=True,
                        help_text=(
                            "Replace this placeholder driver with the extracted workbook "
                            "sub-question."
                        ),
                    ),
                ],
            )
        ],
        overall_outcome="Does Not Meet",
        outcome_justification="Placeholder canonical template generated from workbook upload.",
    )
