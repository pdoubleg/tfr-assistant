"""Stateful lightweight Monty runtime for one artifact session."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from app.capabilities.monty.collections import MontyRuntimeContext, build_monty_registry
from app.capabilities.monty.help_content import HelpTarget, render_help
from app.capabilities.monty.interpreter import CodeExecutionError, MontyReplInterpreter
from app.core.config import Settings
from app.models.chat_state import TFRChatState


class MontyExecutionRecord(BaseModel):
    execution_id: int
    executed_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    code: str
    status: str
    summary: str
    stdout: str = ""
    handles: list[dict[str, Any]] = Field(default_factory=list)
    variables: list[str] = Field(default_factory=list)
    variable_persistence_failures: list[dict[str, str]] = Field(default_factory=list)
    rlm: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    error_details: dict[str, Any] | None = None
    traceback: str | None = None
    retryable: bool = False
    model_guidance: str | None = None


class MontyPythonRuntime:
    def __init__(self, state: TFRChatState, settings: Settings) -> None:
        self.context = MontyRuntimeContext(state=state, settings=settings)
        self.registry = build_monty_registry(self.context)
        self.interpreter = MontyReplInterpreter(tools=self.registry.exported_tools())
        self._execution_counter = 0

    def bind(self, state: TFRChatState, settings: Settings) -> None:
        self.context.state = state
        self.context.settings = settings

    def help(self, name: HelpTarget = None) -> str:
        return render_help(self.registry, name=name)

    async def execute(self, code: str, *, restart: bool = False) -> dict[str, Any]:
        status = "success"
        stdout = ""
        variables: list[str] = []
        variable_persistence_failures: list[dict[str, str]] = []
        error: str | None = None
        error_details: dict[str, Any] | None = None
        formatted_traceback: str | None = None
        retryable = False
        model_guidance: str | None = None
        before_handles = {handle.handle for handle in self.context.state.handles}
        before_rlm_calls = self.context.rlm_call_count

        try:
            if restart:
                self.interpreter.restart()
                self.context.reset_rlm_tracking()
                before_rlm_calls = 0
            result = await self.interpreter.execute(code)
            stdout = result.stdout
            variables = result.persisted_names
            variable_persistence_failures = result.persistence_failures
        except CodeExecutionError as exc:
            status = "error"
            error = _summarize_error_message(str(exc))
            stdout = exc.stdout
            error_details = _error_details(exc, message=error, stdout=stdout)
            retryable = True
            model_guidance = _model_guidance(error)
        except (SyntaxError, PermissionError, ValueError, TypeError) as exc:
            status = "error"
            error = _summarize_error_message(str(exc))
            error_details = _error_details(exc, message=error)
            retryable = True
            model_guidance = _model_guidance(error)
        except Exception as exc:  # pragma: no cover
            status = "error"
            error = _summarize_error_message(f"Unexpected execution failure: {exc}")
            error_details = _error_details(exc, message=error)

        new_handles = [
            handle.model_dump()
            for handle in self.context.state.handles
            if handle.handle not in before_handles
        ]
        summary = (
            "Execution succeeded"
            if status == "success"
            else f"Execution failed: {error or 'unknown error'}"
        )
        if status == "success" and new_handles:
            summary += f"; created {len(new_handles)} handle(s)"
        if status == "success" and variables:
            summary += f"; persisted variable(s): {', '.join(variables)}"
        if status == "success" and stdout:
            summary += f"; captured {len(stdout.splitlines())} stdout line(s)"
        if status == "error" and stdout:
            summary += f"; captured {len(stdout.splitlines())} stdout line(s) before error"
        rlm = self.context.rlm_tracking_payload()
        rlm_call_delta = int(rlm["call_count"]) - before_rlm_calls
        if rlm_call_delta:
            summary += (
                f"; used {rlm_call_delta} sub-LLM call(s) "
                f"({rlm['call_count']}/{rlm['max_llm_calls']})"
            )
        summary += "."

        self._execution_counter += 1
        return MontyExecutionRecord(
            execution_id=self._execution_counter,
            code=code,
            status=status,
            summary=summary,
            stdout=stdout,
            handles=new_handles,
            variables=variables,
            variable_persistence_failures=variable_persistence_failures,
            rlm=rlm,
            error=error,
            error_details=error_details,
            traceback=formatted_traceback,
            retryable=retryable,
            model_guidance=model_guidance,
        ).model_dump()


_ERROR_PREFIX_RE = re.compile(r"^(?P<type>[A-Za-z_][\w.]*?(?:Error|Exception)):\s+")


def _summarize_error_message(message: str) -> str:
    lines = [line.strip() for line in message.splitlines() if line.strip()]
    if not lines:
        return "Unknown execution error"
    for line in reversed(lines):
        if _ERROR_PREFIX_RE.match(line):
            return line
    return lines[-1]


def _error_type_from_message(message: str, fallback: str) -> str:
    match = _ERROR_PREFIX_RE.match(message)
    if match:
        return match.group("type").rsplit(".", maxsplit=1)[-1]
    return fallback


def _model_guidance(error: str) -> str:
    return (
        "This Python sandbox execution failed before the requested result can be assumed "
        f"rendered. Fix the code and call python_sandbox_execute again. Error: {error}"
    )


def _error_details(
    exc: BaseException,
    *,
    message: str | None = None,
    stdout: str = "",
) -> dict[str, Any]:
    concise_message = message or _summarize_error_message(str(exc))
    return {
        "error_type": _error_type_from_message(concise_message, type(exc).__name__),
        "message": concise_message,
        "stdout_before_error": stdout,
    }
