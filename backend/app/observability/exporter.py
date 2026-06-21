from __future__ import annotations

import asyncio
import logging
import threading
from collections.abc import Sequence
from typing import Any

from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult

from app.core.config import Settings
from app.db.session import AsyncSessionLocal
from app.observability.repository import ObservabilityRepository
from app.observability.spans import normalize_readable_span

logger = logging.getLogger(__name__)


def _run_async_safely(coro: Any) -> None:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        asyncio.run(coro)
        return

    error: BaseException | None = None

    def runner() -> None:
        nonlocal error
        try:
            asyncio.run(coro)
        except BaseException as exc:
            error = exc

    thread = threading.Thread(target=runner, name="audit-observability-export", daemon=True)
    thread.start()
    thread.join()
    if error is not None:
        raise error


class AuditDBSpanExporter(SpanExporter):
    """OpenTelemetry exporter that persists audit-generation spans locally."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._shutdown = False
        self._lock = threading.Lock()

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        if self._shutdown or not spans:
            return SpanExportResult.SUCCESS
        normalized = [normalize_readable_span(span) for span in spans]
        try:
            with self._lock:
                _run_async_safely(self._persist(normalized))
        except Exception:
            logger.exception("Failed to persist audit observability spans")
            return SpanExportResult.FAILURE
        return SpanExportResult.SUCCESS

    async def _persist(self, spans: list[dict[str, Any]]) -> None:
        async with AsyncSessionLocal() as session:
            await ObservabilityRepository(session, self.settings).ingest_spans(spans)

    def shutdown(self) -> None:
        self._shutdown = True

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        del timeout_millis
        return True
