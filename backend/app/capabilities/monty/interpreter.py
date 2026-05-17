"""Focused pydantic-monty interpreter for handle-oriented Python repl code."""

from __future__ import annotations

import ast
import asyncio
import inspect
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

import pydantic_monty

DEFAULT_RESOURCE_LIMITS: pydantic_monty.ResourceLimits = {
    "max_memory": 64_000_000,
    "max_recursion_depth": 50,
    "max_allocations": 200_000,
    "gc_interval": 1_000,
}


class CodeExecutionError(RuntimeError):
    """Raised when Monty code fails in a user-facing way."""

    def __init__(self, message: str, *, stdout: str = "") -> None:
        super().__init__(message)
        self.stdout = stdout


class _TopLevelNameCollector:
    """Collect module-scope names that should be visible in later REPL calls."""

    def collect(self, code: str) -> tuple[list[str], list[str]]:
        assigned_names: set[str] = set()
        deleted_names: set[str] = set()
        module = ast.parse(code)
        for statement in module.body:
            self._visit_statement(statement, assigned_names, deleted_names)
        return sorted(assigned_names), sorted(deleted_names)

    def _visit_block(
        self,
        statements: list[ast.stmt],
        assigned_names: set[str],
        deleted_names: set[str],
    ) -> None:
        for statement in statements:
            self._visit_statement(statement, assigned_names, deleted_names)

    def _visit_statement(
        self,
        statement: ast.stmt,
        assigned_names: set[str],
        deleted_names: set[str],
    ) -> None:
        if isinstance(statement, ast.Assign):
            for target in statement.targets:
                self._record_target(target, assigned_names)
            return
        if isinstance(statement, ast.AnnAssign):
            if statement.value is not None:
                self._record_target(statement.target, assigned_names)
            return
        if isinstance(statement, ast.AugAssign):
            self._record_target(statement.target, assigned_names)
            return
        if isinstance(statement, (ast.For, ast.AsyncFor)):
            self._record_target(statement.target, assigned_names)
            self._visit_block(statement.body, assigned_names, deleted_names)
            self._visit_block(statement.orelse, assigned_names, deleted_names)
            return
        if isinstance(statement, (ast.With, ast.AsyncWith)):
            for item in statement.items:
                if item.optional_vars is not None:
                    self._record_target(item.optional_vars, assigned_names)
            self._visit_block(statement.body, assigned_names, deleted_names)
            return
        if isinstance(statement, ast.If):
            self._visit_block(statement.body, assigned_names, deleted_names)
            self._visit_block(statement.orelse, assigned_names, deleted_names)
            return
        if isinstance(statement, ast.While):
            self._visit_block(statement.body, assigned_names, deleted_names)
            self._visit_block(statement.orelse, assigned_names, deleted_names)
            return
        if isinstance(statement, ast.Try):
            self._visit_block(statement.body, assigned_names, deleted_names)
            self._visit_block(statement.orelse, assigned_names, deleted_names)
            self._visit_block(statement.finalbody, assigned_names, deleted_names)
            for handler in statement.handlers:
                self._visit_block(handler.body, assigned_names, deleted_names)
            return
        if isinstance(statement, ast.Match):
            for case in statement.cases:
                self._record_pattern(case.pattern, assigned_names)
                self._visit_block(case.body, assigned_names, deleted_names)
            return
        if isinstance(statement, ast.Delete):
            for target in statement.targets:
                self._record_target(target, deleted_names)

    def _record_pattern(self, pattern: ast.pattern, names: set[str]) -> None:
        for node in ast.walk(pattern):
            if isinstance(node, ast.MatchAs) and node.name:
                names.add(node.name)
            elif isinstance(node, ast.MatchStar) and node.name:
                names.add(node.name)

    def _record_target(self, target: ast.expr, names: set[str]) -> None:
        if isinstance(target, ast.Name):
            names.add(target.id)
            return
        if isinstance(target, (ast.Tuple, ast.List)):
            for element in target.elts:
                self._record_target(element, names)


@dataclass(slots=True)
class InterpreterRunResult:
    stdout: str
    persisted_names: list[str]
    persistence_failures: list[dict[str, str]]


class MontyReplInterpreter:
    """Run code through a persistent Monty REPL with registered host tools."""

    _persist_tool_name = "monty_repl_persist"
    _delete_tool_name = "monty_repl_delete"
    _persist_error_tool_name = "monty_repl_persist_error"

    def __init__(
        self,
        *,
        tools: Mapping[str, Callable[..., Any]],
        name_resolver: Callable[[str], Any | None] | None = None,
        limits: pydantic_monty.ResourceLimits | None = None,
    ) -> None:
        self._tools = dict(tools)
        self._name_resolver = name_resolver
        self._limits = limits or DEFAULT_RESOURCE_LIMITS
        self._state: dict[str, Any] = {}
        self._name_collector = _TopLevelNameCollector()
        self._repl = self._create_repl()

    def _create_repl(self) -> pydantic_monty.MontyRepl:
        return pydantic_monty.MontyRepl(
            limits=self._limits,
            type_check=False,
        )

    @property
    def state(self) -> dict[str, Any]:
        """Return values captured from previous successful REPL executions."""
        return dict(self._state)

    def restart(self) -> None:
        """Reset REPL execution state and host-visible variable captures."""
        self._state.clear()
        self._repl = self._create_repl()

    @staticmethod
    def _matches_monty_exception(exc: BaseException, exception_name: str) -> bool:
        exported_type = getattr(pydantic_monty, exception_name, None)
        if isinstance(exported_type, type) and issubclass(exported_type, BaseException):
            return isinstance(exc, exported_type)
        return type(exc).__name__ == exception_name

    def _raise_known_monty_error(self, exc: BaseException, *, stdout: str = "") -> None:
        if self._matches_monty_exception(exc, "MontySyntaxError"):
            raise SyntaxError(self._monty_error_message(exc)) from exc
        if self._matches_monty_exception(exc, "MontyTypingError"):
            raise CodeExecutionError(self._monty_error_message(exc), stdout=stdout) from exc
        if self._matches_monty_exception(exc, "MontyRuntimeError"):
            raise CodeExecutionError(self._monty_error_message(exc), stdout=stdout) from exc
        raise exc

    @staticmethod
    def _monty_error_message(exc: BaseException) -> str:
        display = getattr(exc, "display", None)
        if callable(display):
            return str(display())
        return str(exc)

    def _start_monty(
        self,
        code: str,
        print_callback: Callable[[str, str], None],
        *,
        tools: Mapping[str, Callable[..., Any]] | None = None,
    ) -> (
        pydantic_monty.FunctionSnapshot
        | pydantic_monty.NameLookupSnapshot
        | pydantic_monty.FutureSnapshot
        | pydantic_monty.MontyComplete
    ):
        try:
            return self._repl.feed_start(
                code,
                inputs=tools or self._tools,
                print_callback=print_callback,
            )
        except Exception as exc:
            self._raise_known_monty_error(exc)
            raise

    def _wrap_code(self, code: str, assigned_names: list[str], deleted_names: list[str]) -> str:
        lines = [code.rstrip(), ""]
        for name in assigned_names:
            if name in {
                self._persist_tool_name,
                self._delete_tool_name,
                self._persist_error_tool_name,
            }:
                continue
            lines.extend(
                [
                    "try:",
                    f"    {self._persist_tool_name}({name!r}, {name})",
                    "except Exception as exc:",
                    (
                        f"    {self._persist_error_tool_name}"
                        f"({name!r}, str(exc).strip() or exc.__class__.__name__)"
                    ),
                    "",
                ]
            )
        for name in deleted_names:
            lines.append(f"{self._delete_tool_name}({name!r})")
        return "\n".join(lines).strip() + "\n"

    @staticmethod
    def _resume_function_snapshot(
        snapshot: pydantic_monty.FunctionSnapshot,
        result: pydantic_monty.ExternalResult,
    ) -> (
        pydantic_monty.FunctionSnapshot
        | pydantic_monty.NameLookupSnapshot
        | pydantic_monty.FutureSnapshot
        | pydantic_monty.MontyComplete
    ):
        try:
            return snapshot.resume(result)
        except TypeError:
            if not result or len(result) != 1:
                raise
            key, value = next(iter(result.items()))
            return snapshot.resume(**{key: value})

    @staticmethod
    def _resume_future_snapshot(
        snapshot: pydantic_monty.FutureSnapshot,
        results: dict[int, pydantic_monty.ExternalResult],
    ) -> (
        pydantic_monty.FunctionSnapshot
        | pydantic_monty.NameLookupSnapshot
        | pydantic_monty.FutureSnapshot
        | pydantic_monty.MontyComplete
    ):
        return snapshot.resume(results)

    async def execute(self, code: str) -> InterpreterRunResult:
        assigned_names, deleted_names = self._name_collector.collect(code)
        captured_state: dict[str, Any] = {}
        deleted_state_names: set[str] = set()
        persistence_failures: list[dict[str, str]] = []
        stdout_parts: list[str] = []

        def capture_print(_stream: str, text: str) -> None:
            stdout_parts.append(text)

        def persist_variable(name: str, value: Any) -> None:
            captured_state[name] = value

        def delete_variable(name: str) -> None:
            deleted_state_names.add(name)

        def record_persist_failure(name: str, error: str) -> None:
            persistence_failures.append({"name": name, "error": error})

        persist_variable.__name__ = self._persist_tool_name
        delete_variable.__name__ = self._delete_tool_name
        record_persist_failure.__name__ = self._persist_error_tool_name

        external_tools = dict(self._tools)
        external_tools[self._persist_tool_name] = persist_variable
        external_tools[self._delete_tool_name] = delete_variable
        external_tools[self._persist_error_tool_name] = record_persist_failure
        try:
            progress = self._start_monty(
                self._wrap_code(code, assigned_names, deleted_names),
                capture_print,
                tools=external_tools,
            )
        except CodeExecutionError as exc:
            raise CodeExecutionError(str(exc), stdout="".join(stdout_parts)) from exc
        pending_tasks: dict[int, asyncio.Task[pydantic_monty.ExternalResult]] = {}

        async def resolve_async_tool(result: Any) -> pydantic_monty.ExternalResult:
            try:
                return {"return_value": await result}
            except Exception as exc:  # pragma: no cover
                return {"exception": exc}

        try:
            while not isinstance(progress, pydantic_monty.MontyComplete):
                if isinstance(progress, pydantic_monty.NameLookupSnapshot):
                    if progress.variable_name in external_tools:
                        progress = progress.resume(value=external_tools[progress.variable_name])
                        continue
                    value = (
                        self._name_resolver(progress.variable_name)
                        if self._name_resolver is not None
                        else None
                    )
                    progress = (
                        progress.resume(value=value) if value is not None else progress.resume()
                    )
                    continue

                if isinstance(progress, pydantic_monty.FunctionSnapshot):
                    func = external_tools.get(progress.function_name)
                    if func is None:
                        progress = self._resume_function_snapshot(
                            progress,
                            {"exception": NameError(f"Unknown function: {progress.function_name}")},
                        )
                        continue
                    try:
                        result = func(*progress.args, **progress.kwargs)
                    except Exception as exc:
                        progress = self._resume_function_snapshot(progress, {"exception": exc})
                        continue
                    if inspect.iscoroutine(result):
                        pending_tasks[progress.call_id] = asyncio.create_task(
                            resolve_async_tool(result)
                        )
                        progress = self._resume_function_snapshot(progress, {"future": ...})
                        continue
                    progress = self._resume_function_snapshot(progress, {"return_value": result})
                    continue

                if isinstance(progress, pydantic_monty.FutureSnapshot):
                    results: dict[int, pydantic_monty.ExternalResult] = {}
                    gather_ids = [
                        call_id for call_id in progress.pending_call_ids if call_id in pending_tasks
                    ]
                    if gather_ids:
                        settled = await asyncio.gather(
                            *(pending_tasks[call_id] for call_id in gather_ids),
                            return_exceptions=True,
                        )
                        for call_id, outcome in zip(gather_ids, settled, strict=False):
                            pending_tasks.pop(call_id, None)
                            results[call_id] = (
                                {"exception": outcome}
                                if isinstance(outcome, Exception)
                                else outcome
                            )
                    progress = self._resume_future_snapshot(progress, results)
                    continue

                raise CodeExecutionError(
                    f"Unexpected Monty progress type: {type(progress).__name__}"
                )
        except CodeExecutionError as exc:
            if exc.stdout:
                raise
            raise CodeExecutionError(str(exc), stdout="".join(stdout_parts)) from exc
        except Exception as exc:
            self._raise_known_monty_error(exc, stdout="".join(stdout_parts))
            raise
        finally:
            for task in pending_tasks.values():
                task.cancel()
            if pending_tasks:
                await asyncio.gather(*pending_tasks.values(), return_exceptions=True)

        self._state.update(captured_state)
        for deleted_name in deleted_state_names:
            self._state.pop(deleted_name, None)

        return InterpreterRunResult(
            stdout="".join(stdout_parts),
            persisted_names=sorted(captured_state),
            persistence_failures=persistence_failures,
        )
