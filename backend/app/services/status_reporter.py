import json
from dataclasses import dataclass
from typing import Literal, Protocol
from uuid import uuid4

from app.models.chat_state import ActivityLogEntry, TFRChatState, log_activity

ActivityStatus = Literal["in_progress", "completed", "error"]


class StatusReporter(Protocol):
    def update(
        self,
        message: str,
        status: ActivityStatus = "in_progress",
        *,
        progress: int | None = None,
    ) -> None: ...

    def in_progress(self, message: str, *, progress: int | None = None) -> None: ...

    def completed(self, message: str, *, progress: int | None = None) -> None: ...

    def error(self, message: str, *, progress: int | None = None) -> None: ...


class NullStatusReporter:
    def update(
        self,
        message: str,
        status: ActivityStatus = "in_progress",
        *,
        progress: int | None = None,
    ) -> None:
        del message, status, progress

    def in_progress(self, message: str, *, progress: int | None = None) -> None:
        self.update(message, "in_progress", progress=progress)

    def completed(self, message: str, *, progress: int | None = None) -> None:
        self.update(message, "completed", progress=progress)

    def error(self, message: str, *, progress: int | None = None) -> None:
        self.update(message, "error", progress=progress)


def record_tool_call_started(
    state: TFRChatState,
    *,
    source_name: str,
    tool_name: str,
    args: dict[str, object],
    tool_call_id: str | None = None,
) -> None:
    formatted_name = _format_tool_name(tool_name)
    message = f"{formatted_name} running."
    state.status = "using_tools"
    state.current_step = message
    state.error_message = None
    state.activity_log.append(
        ActivityLogEntry(
            id=f"{source_name}-{tool_call_id or uuid4().hex}",
            message=message,
            status="in_progress",
            code=_tool_args_code(tool_name, args),
        )
    )


def _tool_args_code(tool_name: str, args: dict[str, object]) -> dict[str, object] | None:
    if not args:
        return None
    return {
        "code": json.dumps(args, indent=2, sort_keys=True, default=str),
        "language": "json",
        "title": "Arguments",
        "caption": tool_name,
        "defaultOpen": False,
    }


def _format_tool_name(name: str) -> str:
    return name.replace("_", " ").title()


@dataclass(slots=True)
class ChatStateStatusReporter:
    state: TFRChatState
    source_name: str = "audit_form_generation"
    user_visible_errors: bool = True

    def update(
        self,
        message: str,
        status: ActivityStatus = "in_progress",
        *,
        progress: int | None = None,
    ) -> None:
        self.state.status = (
            "error" if status == "error" and self.user_visible_errors else "using_tools"
        )
        self.state.current_step = message
        if status == "error" and self.user_visible_errors:
            self.state.error_message = message
        else:
            self.state.error_message = None
        if progress is not None:
            self.state.progress = max(self.state.progress, progress)
        log_activity(self.state, message, status, self.source_name)

    def in_progress(self, message: str, *, progress: int | None = None) -> None:
        self.update(message, "in_progress", progress=progress)

    def completed(self, message: str, *, progress: int | None = None) -> None:
        self.update(message, "completed", progress=progress)

    def error(self, message: str, *, progress: int | None = None) -> None:
        self.update(message, "error", progress=progress)
