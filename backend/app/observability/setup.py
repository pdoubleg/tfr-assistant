from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.config import Settings
from app.observability.context import apply_context_to_span

logger = logging.getLogger(__name__)

_configured = False


class AuditContextSpanProcessor:
    def on_start(
        self,
        span: object,
        parent_context: object | None = None,
    ) -> None:
        del parent_context
        apply_context_to_span(span)

    def on_end(self, span: object) -> None:
        del span

    def shutdown(self) -> None:
        return None

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        del timeout_millis
        return True


def configure_observability(
    app: FastAPI,
    *,
    settings: Settings,
    engine: AsyncEngine,
) -> None:
    global _configured
    if _configured or not settings.observability_enabled:
        return

    try:
        from opentelemetry import trace
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import SpanProcessor, TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except Exception as exc:
        logger.warning("OpenTelemetry SDK is not available; observability disabled: %s", exc)
        return

    resource = Resource.create(
        {
            "service.name": settings.otel_service_name,
            "deployment.environment": settings.environment,
            "service.version": settings.app_version,
        }
    )
    provider = TracerProvider(resource=resource)

    class _AuditContextSpanProcessor(AuditContextSpanProcessor, SpanProcessor):
        pass

    provider.add_span_processor(_AuditContextSpanProcessor())

    if settings.observability_local_export_enabled:
        try:
            from app.observability.exporter import AuditDBSpanExporter

            provider.add_span_processor(BatchSpanProcessor(AuditDBSpanExporter(settings)))
        except Exception as exc:
            logger.warning("Local audit span exporter could not be configured: %s", exc)

    if settings.observability_otlp_enabled:
        _add_otlp_exporter(provider, settings)

    try:
        trace.set_tracer_provider(provider)
    except Exception as exc:
        logger.warning("OpenTelemetry tracer provider was already configured: %s", exc)

    _instrument_fastapi(app)
    _instrument_sqlalchemy(engine)
    _instrument_pydantic_ai(settings, provider)
    _configured = True


def _add_otlp_exporter(provider: Any, settings: Settings) -> None:
    try:
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except Exception as exc:
        logger.warning("OTLP trace exporter is not available: %s", exc)
        return

    endpoint = (
        settings.otel_exporter_otlp_traces_endpoint
        or settings.otel_exporter_otlp_endpoint
        or "http://localhost:4318/v1/traces"
    )
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))


def _instrument_fastapi(app: FastAPI) -> None:
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    except Exception:
        logger.info(
            "opentelemetry-instrumentation-fastapi is not installed; skipping FastAPI spans"
        )
        return
    try:
        FastAPIInstrumentor.instrument_app(app)
    except Exception as exc:
        logger.warning("FastAPI instrumentation failed: %s", exc)


def _instrument_sqlalchemy(engine: AsyncEngine) -> None:
    try:
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
    except Exception:
        logger.info("opentelemetry-instrumentation-sqlalchemy is not installed; skipping DB spans")
        return
    try:
        SQLAlchemyInstrumentor().instrument(engine=engine.sync_engine)
    except Exception as exc:
        logger.warning("SQLAlchemy instrumentation failed: %s", exc)


def _instrument_pydantic_ai(settings: Settings, provider: Any) -> None:
    try:
        from pydantic_ai import Agent
        from pydantic_ai.models.instrumented import InstrumentationSettings
    except Exception as exc:
        logger.warning("Pydantic AI instrumentation is not available: %s", exc)
        return

    version = settings.pydantic_ai_instrumentation_version
    if version not in {1, 2, 3, 4, 5}:
        version = 2
    try:
        Agent.instrument_all(
            InstrumentationSettings(
                tracer_provider=provider,
                include_content=settings.pydantic_ai_otel_include_content,
                include_binary_content=settings.pydantic_ai_include_binary_content,
                version=version,  # type: ignore[arg-type]
                use_aggregated_usage_attribute_names=True,
            )
        )
    except Exception as exc:
        logger.warning("Pydantic AI instrumentation failed: %s", exc)
