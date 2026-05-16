"""Stateful lightweight Monty runtime for one artifact session."""

from __future__ import annotations

import traceback
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
    error: str | None = None
    traceback: str | None = None


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

    async def execute(self, code: str) -> dict[str, Any]:
        status = "success"
        stdout = ""
        error: str | None = None
        formatted_traceback: str | None = None
        before_handles = {handle.handle for handle in self.context.state.handles}

        try:
            result = await self.interpreter.execute(code)
            stdout = result.stdout
        except (CodeExecutionError, SyntaxError, PermissionError, ValueError, TypeError) as exc:
            status = "error"
            error = str(exc)
            formatted_traceback = traceback.format_exc()
        except Exception as exc:  # pragma: no cover
            status = "error"
            error = f"Unexpected execution failure: {exc}"
            formatted_traceback = traceback.format_exc()

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
        if status == "success" and stdout:
            summary += f"; captured {len(stdout.splitlines())} stdout line(s)"
        summary += "."

        self._execution_counter += 1
        return MontyExecutionRecord(
            execution_id=self._execution_counter,
            code=code,
            status=status,
            summary=summary,
            stdout=stdout,
            handles=new_handles,
            error=error,
            traceback=formatted_traceback,
        ).model_dump()
