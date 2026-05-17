from dataclasses import dataclass
from typing import Literal, Protocol

from app.models.chat_state import TFRChatState, log_activity

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
