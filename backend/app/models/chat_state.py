"""Shared AG-UI chat state for the TFR assistant."""

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class ActivityLogEntry(BaseModel):
    id: str
    message: str
    timestamp: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    status: Literal["in_progress", "completed", "error"] = "in_progress"


class TFRChatState(BaseModel):
    """Frontend/backend state synchronized through AG-UI."""

    active_route: str = "/"
    active_review_id: str | None = None
    selected_form_ids: list[str] = Field(default_factory=list)
    documents: list[dict[str, Any]] = Field(default_factory=list)
    status: Literal["idle", "thinking", "using_tools", "complete", "error"] = "idle"
    progress: int = 0
    current_step: str = ""
    activity_log: list[ActivityLogEntry] = Field(default_factory=list)
    error_message: str | None = None


def log_activity(
    state: TFRChatState,
    message: str,
    status: Literal["in_progress", "completed", "error"],
    source: str,
) -> None:
    state.activity_log.append(
        ActivityLogEntry(
            id=f"{source}-{len(state.activity_log) + 1}",
            message=message,
            status=status,
        )
    )
