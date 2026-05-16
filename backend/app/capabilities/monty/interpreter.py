"""Focused pydantic-monty interpreter for handle-oriented sandbox code."""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

import pydantic_monty


class CodeExecutionError(RuntimeError):
    """Raised when Monty code fails in a user-facing way."""


@dataclass(slots=True)
class InterpreterRunResult:
    stdout: str


class MontyReplInterpreter:
    """Run code through a persistent Monty REPL with registered host tools."""

    def __init__(
        self,
        *,
        tools: Mapping[str, Callable[..., Any]],
        limits: pydantic_monty.ResourceLimits | None = None,
    ) -> None:
        self._tools = dict(tools)
        self._repl = pydantic_monty.MontyRepl(
            limits=limits
            or {
                "max_duration_secs": 20,
                "max_memory": 64_000_000,
                "max_recursion_depth": 50,
                "max_allocations": 200_000,
                "gc_interval": 1_000,
            },
            type_check=False,
        )

    @staticmethod
    def _matches_monty_exception(exc: BaseException, exception_name: str) -> bool:
        exported_type = getattr(pydantic_monty, exception_name, None)
        if isinstance(exported_type, type) and issubclass(exported_type, BaseException):
            return isinstance(exc, exported_type)
        return type(exc).__name__ == exception_name

    def _raise_known_monty_error(self, exc: BaseException) -> None:
        if self._matches_monty_exception(exc, "MontySyntaxError"):
            raise SyntaxError(str(exc)) from exc
        if self._matches_monty_exception(exc, "MontyTypingError"):
            raise CodeExecutionError(str(exc)) from exc
        if self._matches_monty_exception(exc, "MontyRuntimeError"):
            raise CodeExecutionError(str(exc)) from exc
        raise exc

    def _start_monty(
        self,
        code: str,
        print_callback: Callable[[str, str], None],
    ) -> (
        pydantic_monty.FunctionSnapshot
        | pydantic_monty.NameLookupSnapshot
        | pydantic_monty.FutureSnapshot
        | pydantic_monty.MontyComplete
    ):
        try:
            return self._repl.feed_start(
                code,
                inputs=self._tools,
                print_callback=print_callback,
            )
        except Exception as exc:
            self._raise_known_monty_error(exc)
            raise

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
        stdout_parts: list[str] = []

        def capture_print(_stream: str, text: str) -> None:
            stdout_parts.append(text)

        progress = self._start_monty(code, capture_print)
        pending_tasks: dict[int, asyncio.Task[pydantic_monty.ExternalResult]] = {}

        async def resolve_async_tool(result: Any) -> pydantic_monty.ExternalResult:
            try:
                return {"return_value": await result}
            except Exception as exc:  # pragma: no cover
                return {"exception": exc}

        try:
            while not isinstance(progress, pydantic_monty.MontyComplete):
                if isinstance(progress, pydantic_monty.NameLookupSnapshot):
                    value = self._tools.get(progress.variable_name)
                    progress = (
                        progress.resume(value=value) if value is not None else progress.resume()
                    )
                    continue

                if isinstance(progress, pydantic_monty.FunctionSnapshot):
                    func = self._tools.get(progress.function_name)
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
        except Exception as exc:
            self._raise_known_monty_error(exc)
            raise

        return InterpreterRunResult(stdout="".join(stdout_parts))
