"""Pydantic-AI capability exposing a lightweight Monty Python sandbox."""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import uuid4

from ag_ui.core import EventType, StateSnapshotEvent
from pydantic_ai import FunctionToolset, RunContext, ToolReturn
from pydantic_ai.capabilities import AbstractCapability
from pydantic_ai.toolsets import AbstractToolset, PrefixedToolset

from app.capabilities.deps import TFRChatDeps
from app.capabilities.monty.help_content import SANDBOX_GUIDANCE, HelpTarget
from app.capabilities.monty.runtime import MontyPythonRuntime
from app.services.status_reporter import ChatStateStatusReporter


@dataclass(slots=True)
class MontyPythonCapability(AbstractCapability[TFRChatDeps]):
    """Expose handle-oriented Python composition through Monty."""

    _runtimes: dict[str, MontyPythonRuntime] = field(default_factory=dict)

    def get_instructions(self) -> str:
        return (
            SANDBOX_GUIDANCE + " In this agent, the sandbox tools are exposed as "
            "`python_sandbox_help(name=...)` and `python_sandbox_execute(code=...)` "
            "to avoid colliding with the SQL execute tool."
        )

    def get_toolset(self) -> AbstractToolset[TFRChatDeps]:
        toolset = FunctionToolset[TFRChatDeps](
            id="python_sandbox",
            instructions=(
                "Use this sandbox after SQL has persisted a dataset handle with "
                "persist_result=true. Prefer python_sandbox_help() before using "
                "unfamiliar collections or helpers; call it with no name for the "
                "overview, a collection name for related helpers, a helper name "
                "for full details, or a list of names to fetch several docs at "
                "once. Use python_sandbox_execute(code=...) for multi-step handle "
                "transforms and Plotly rendering. Registered helpers are already "
                "available by name inside the sandbox, so do not import helpers "
                "or data libraries. Only use limited imports such as math, json, "
                "or re for small scalar/string work."
            ),
        )

        @toolset.tool(docstring_format="google", require_parameter_descriptions=True)
        async def help(
            ctx: RunContext[TFRChatDeps],
            name: HelpTarget = None,
        ) -> str:
            """Describe available Monty sandbox collections and helper functions.

            Use this before writing sandbox code when a helper name, collection
            purpose, parameter shape, or return value is unfamiliar. Calling
            without a name returns the collection overview. Passing a collection
            name lists that collection's helpers. Passing a helper name returns
            the helper signature and usage notes. Passing a list of names returns
            the requested help blocks appended together.

            Args:
                name: Optional collection or helper name, or list of collection
                    and helper names to inspect. Use None for the high-level
                    sandbox overview.

            Returns:
                Formatted help text sourced from registered function signatures
                and docstrings.
            """
            return self._runtime(ctx).help(name=name)

        @toolset.tool(docstring_format="google", require_parameter_descriptions=True)
        async def execute(
            ctx: RunContext[TFRChatDeps],
            code: str,
        ) -> ToolReturn:
            """Execute Monty-sandboxed Python for dataframe handles and Plotly charts.

            Use this after SQL has created a dataset handle with
            persist_result=true, or after a previous sandbox step created a
            handle. The code can call registered helper functions such as
            list_handles(), get_dataset(), group_by(), value_counts(),
            create_bar_chart(), and emit_plotly_chart(). It may compose multiple
            helper calls in one execution and can use print() for diagnostics.
            Helpers are already present in the sandbox namespace, so call them
            directly without imports. Do not import pandas, numpy, scipy, or
            plotly; use registered helper functions for dataframe transforms and
            visualization. Limited imports such as math, json, and re are
            available for simple scalar/string work. Do not attempt to run SQL
            here; SQL remains the database gatekeeper.

            Args:
                code: Python source code to run inside the restrictive Monty
                    sandbox. Prefer registered helper functions over imports,
                    and keep data references behind dataset or chart handle strings.

            Returns:
                ToolReturn containing execution status, captured stdout, any new
                handles, emitted chat components, and error details when the
                sandboxed code fails.
            """
            state = ctx.deps.state
            reporter = ChatStateStatusReporter(state, source_name="monty_execute")
            reporter.in_progress("Executing Python sandbox code...", progress=35)
            result = await self._runtime(ctx).execute(code)
            if result["status"] == "error":
                reporter.error(str(result["error"]), progress=100)
            else:
                reporter.completed(str(result["summary"]), progress=100)
                state.status = "complete"
            return ToolReturn(
                return_value=result,
                metadata=[StateSnapshotEvent(type=EventType.STATE_SNAPSHOT, snapshot=state)],
            )

        return PrefixedToolset(toolset, prefix="python_sandbox")

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
