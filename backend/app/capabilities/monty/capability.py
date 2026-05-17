"""Pydantic-AI capability exposing a lightweight Monty Python repl."""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import uuid4

from ag_ui.core import EventType, StateSnapshotEvent
from pydantic_ai import FunctionToolset, RunContext, ToolReturn
from pydantic_ai.capabilities import AbstractCapability
from pydantic_ai.toolsets import AbstractToolset

from app.capabilities.deps import TFRChatDeps
from app.capabilities.monty.help_content import HelpTarget, render_python_repl_guidance
from app.capabilities.monty.runtime import MontyPythonRuntime
from app.services.status_reporter import ChatStateStatusReporter


@dataclass(slots=True)
class MontyPythonCapability(AbstractCapability[TFRChatDeps]):
    """Expose handle-oriented Python composition through Monty."""

    _runtimes: dict[str, MontyPythonRuntime] = field(default_factory=dict)

    def get_instructions(self) -> str:
        return render_python_repl_guidance("python_repl_help")

    def get_toolset(self) -> AbstractToolset[TFRChatDeps]:
        toolset = FunctionToolset[TFRChatDeps](
            id="python_repl",
            instructions=(
                "Use python_repl_help for Python repl discovery and "
                "python_repl_execute for code execution. Keep SQL in SQL tools; "
                "pass persisted dataset handles into the Python repl."
            ),
        )

        @toolset.tool(docstring_format="google", require_parameter_descriptions=True)
        async def python_repl_help(
            ctx: RunContext[TFRChatDeps],
            name: HelpTarget = None,
        ) -> str:
            """Describe available Python repl collections and registered tools.

            Use this before writing Python repl code when a collection, tool
            signature, parameter shape, or return value is unfamiliar.

            Args:
                name: Optional collection or tool name, or list of collection
                    and tool names to inspect. Use None for the high-level
                    Python repl overview.

            Returns:
                Formatted help text sourced from registered tool signatures
                and docstrings.
            """
            return self._runtime(ctx).help(name=name)

        @toolset.tool(docstring_format="google", require_parameter_descriptions=True)
        async def python_repl_execute(
            ctx: RunContext[TFRChatDeps],
            code: str,
            restart: bool = False,
        ) -> ToolReturn:
            """Execute a Python code block in a repl sandbox.

            Use after SQL or earlier Python repl code has produced handles.
            Registered tools are available by name inside the repl; use
            python_repl_help for detailed docs before writing unfamiliar calls.

            Args:
                code: Python source code to run inside the Monty Python repl.
                    Prefer registered tools over imports,
                    and keep data references behind dataset or chart handle strings.
                restart: Whether to reset the REPL state before running code.
                    Defaults to false so variables persist between Python repl calls.

            Returns:
                ToolReturn containing execution status, captured stdout, any new
                handles, emitted chat components, and error details when the
                Python repl code fails.
            """
            state = ctx.deps.state
            reporter = ChatStateStatusReporter(
                state,
                source_name="python_repl_execute",
                user_visible_errors=False,
            )
            reporter.in_progress("Executing Python repl code...", progress=35)
            result = await self._runtime(ctx).execute(code, restart=restart)
            if result["status"] == "error":
                reporter.error("Python repl execution failed.", progress=100)
            else:
                reporter.completed(str(result["summary"]), progress=100)
                state.status = "complete"
            return ToolReturn(
                return_value=result,
                metadata=[StateSnapshotEvent(type=EventType.STATE_SNAPSHOT, snapshot=state)],
            )

        return toolset

    def _runtime(self, ctx: RunContext[TFRChatDeps]) -> MontyPythonRuntime:
        state = ctx.deps.state
        if not state.artifact_session_id:
            state.artifact_session_id = str(uuid4())
        key = state.artifact_session_id
        runtime = self._runtimes.get(key)
        if runtime is None:
            runtime = MontyPythonRuntime(state, ctx.deps.settings)
            self._runtimes[key] = runtime
        runtime.bind(state, ctx.deps.settings)
        return runtime


__all__ = ["MontyPythonCapability"]
