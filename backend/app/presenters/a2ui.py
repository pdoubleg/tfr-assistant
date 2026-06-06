"""Presenter helpers for converting backend data into chat-rendered A2UI payloads."""

from typing import Any

from app.models.a2ui import A2UIComponent
from app.schemas.reviews import ReviewRecord


def generate_data_table(
    headers: list[str],
    rows: list[list[Any]],
    caption: str = "",
    *,
    sortable: bool = True,
    copyable: bool = True,
    downloadable: bool = True,
) -> A2UIComponent:
    """Build a data-table component payload for the chat pane."""

    return A2UIComponent(
        type="a2ui.DataTable",
        props={
            "headers": headers,
            "rows": rows,
            "caption": caption,
            "sortable": sortable,
            "copyable": copyable,
            "downloadable": downloadable,
        },
        layout={"width": "full"},
        zone="chat",
    )


def generate_code_disclosure(
    *,
    code: str,
    language: str,
    title: str,
    caption: str = "",
    default_open: bool = False,
    copyable: bool = True,
) -> A2UIComponent:
    """Build a reusable collapsible code component payload for the chat pane."""

    return A2UIComponent(
        type="a2ui.CodeDisclosure",
        props={
            "code": code,
            "language": language,
            "title": title,
            "caption": caption,
            "defaultOpen": default_open,
            "copyable": copyable,
        },
        layout={"width": "full"},
        zone="chat",
    )


def generate_plotly_chart(
    *,
    figure: dict[str, Any],
    caption: str = "",
    source_handle: str = "",
) -> A2UIComponent:
    """Build a Plotly chart component payload for the chat pane."""

    return A2UIComponent(
        type="a2ui.PlotlyChart",
        props={
            "data": figure.get("data", []),
            "layout": figure.get("layout", {}),
            "config": {
                "displaylogo": False,
                "responsive": True,
            },
            "caption": caption,
            "sourceHandle": source_handle,
        },
        layout={"width": "full"},
        zone="chat",
    )


def generate_artifact_bundle_card(
    *,
    component: str,
    sessionId: str,
    handle: str,
    kind: str,
    title: str,
    subtitle: str = "",
    summary: str = "",
    files: list[dict[str, Any]] | None = None,
    warnings: list[str] | None = None,
    createdAt: str = "",
) -> A2UIComponent:
    """Build a downloadable artifact-bundle card payload for the chat pane."""

    return A2UIComponent(
        type=component,
        props={
            "sessionId": sessionId,
            "handle": handle,
            "kind": kind,
            "title": title,
            "subtitle": subtitle,
            "summary": summary,
            "files": files or [],
            "warnings": warnings or [],
            "createdAt": createdAt,
        },
        layout={"width": "full"},
        zone="chat",
    )


def generate_audit_review_card(review: ReviewRecord) -> A2UIComponent | None:
    """Build a chat card that opens a persisted audit review in the output editor."""

    form = review.user_version or review.original
    if form is None:
        return None
    input_json = review.input_json or {}
    claim_number = input_json.get("claim_number")
    batch_run_name = input_json.get("batch_run_name")
    return A2UIComponent(
        id=f"audit-review-card-{review.id}",
        type="a2ui.AuditReviewCard",
        props={
            "reviewId": review.id,
            "formId": review.form_id,
            "formVersion": review.form_version,
            "title": form.title,
            "description": form.description,
            "claimNumber": claim_number if isinstance(claim_number, str) else "",
            "runName": batch_run_name if isinstance(batch_run_name, str) else "",
            "source": review.source,
            "status": review.status,
            "outcome": form.overall_outcome,
            "createdAt": review.created_at.isoformat(),
            "updatedAt": review.updated_at.isoformat(),
            "form": form.model_dump(mode="json"),
        },
        layout={"width": "full"},
        zone="chat",
    )
