"""Usage and call-budget tracking for Monty RLM tools."""

from __future__ import annotations

import threading
from copy import copy

from pydantic_ai.usage import RequestUsage, RunUsage


class UsageTracker:
    """Thread-safe accumulator for pydantic-ai usage objects."""

    def __init__(self) -> None:
        self._usage = RunUsage()
        self._lock = threading.Lock()

    def incr(self, usage: RunUsage | RequestUsage) -> None:
        with self._lock:
            self._usage.incr(usage)

    @property
    def usage(self) -> RunUsage:
        with self._lock:
            return copy(self._usage)

    def reset(self) -> None:
        with self._lock:
            self._usage = RunUsage()

    def as_dict(self) -> dict[str, object]:
        usage = self.usage
        payload = dict(vars(usage))
        payload["total_tokens"] = usage.total_tokens
        return payload
