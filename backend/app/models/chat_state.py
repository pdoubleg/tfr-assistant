"""Shared AG-UI chat state for the TFR assistant."""

from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field

from app.models.a2ui import A2UIComponent


class ActivityLogEntry(BaseModel):
    id: str
    message: str
    timestamp: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    status: Literal["in_progress", "completed", "error"] = "in_progress"


class ChatHandleMetadata(BaseModel):
    handle: str
    kind: Literal["dataset", "plotly_chart", "report_bundle", "deck_bundle"]
    label: str = ""
    row_count: int | None = None
    column_count: int | None = None
    columns: list[str] = Field(default_factory=list)
    source: str = ""
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


class SelectedHomeRowContext(BaseModel):
    row_id: str
    review_id: str
    result_version: str = "current"
    form_id: str = ""
    form_version: str = ""
    form_kind: str = "standard"
    form_key: str = ""
    claim_number: str = ""
    batch_id: str = ""
    run_name: str = ""
    source: str = ""
    outcome: str = ""
    title: str = ""
    created_at: str = ""
    updated_at: str = ""
    question_count: int = 0
    no_count: int = 0
    driver_count: int = 0
    edited: bool = False
    row_kind: Literal["review", "dataset_case"] = "review"
    dataset_id: str = ""
    dataset_case_id: str = ""
    ground_truth_id: str = ""
    reference_kind: str = ""


class HomeTableFilters(BaseModel):
    search: str = ""
    column_filters: dict[str, str] = Field(default_factory=dict)
    sorting: list[dict[str, Any]] = Field(default_factory=list)
    page_index: int = 0
    page_size: int = 25
    density: str = "normal"


class HomeTableContext(BaseModel):
    selected_rows: list[SelectedHomeRowContext] = Field(default_factory=list)
    visible_row_count: int = 0
    total_row_count: int = 0
    filters: HomeTableFilters = Field(default_factory=HomeTableFilters)


class ChatRunContext(BaseModel):
    active_route: str = "/"
    selected_home_rows: list[SelectedHomeRowContext] = Field(default_factory=list)
    home_table: HomeTableContext = Field(default_factory=HomeTableContext)
    captured_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


class TFRChatState(BaseModel):
    """Frontend/backend state synchronized through AG-UI."""

    active_route: str = "/"
    active_review_id: str | None = None
    selected_form_ids: list[str] = Field(default_factory=list)
    documents: list[dict[str, Any]] = Field(default_factory=list)
    artifact_session_id: str = Field(default_factory=lambda: str(uuid4()))
    handles: list[ChatHandleMetadata] = Field(default_factory=list)
    components: list[A2UIComponent] = Field(default_factory=list)
    run_context: ChatRunContext | None = None
    status: Literal["idle", "thinking", "using_tools", "complete", "error"] = "idle"
    progress: int = 0
    current_step: str = ""
    activity_log: list[ActivityLogEntry] = Field(default_factory=list)
    error_message: str | None = None
    chat_model_name: str = ""
    chat_context_window: int | None = None
    chat_context_used_tokens: int = 0
    chat_context_remaining_percent: float | None = None
    chat_run_cost: float = 0.0
    chat_total_cost: float = 0.0
    chat_last_usage: dict[str, int] = Field(default_factory=dict)


def log_activity(
    state: TFRChatState,
    message: str,
    status: Literal["in_progress", "completed", "error"],
    source: str,
) -> None:
    if status in {"completed", "error"}:
        source_prefix = f"{source}-"
        for entry in state.activity_log:
            if entry.id.startswith(source_prefix) and entry.status == "in_progress":
                entry.status = status

    state.activity_log.append(
        ActivityLogEntry(
            id=f"{source}-{len(state.activity_log) + 1}",
            message=message,
            status=status,
        )
    )
