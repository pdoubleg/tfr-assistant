# Audit Generation Observability

This app captures audit form generation traces through OpenTelemetry and persists them into
application-owned SQLAlchemy tables. Logfire is not required.

## Architecture

- `app.observability.setup.configure_observability()` configures the OpenTelemetry tracer provider,
  resource attributes, local database exporter, optional OTLP export, FastAPI instrumentation,
  SQLAlchemy instrumentation, and Pydantic AI instrumentation.
- `app.observability.context.observed_audit_generation()` starts the root audit-generation span and
  stamps audit metadata into every span created inside the context.
- Pydantic AI spans are emitted by `Agent.instrument_all(...)`.
- `AuditDBSpanExporter` batches finished spans and writes them through
  `ObservabilityRepository`, outside the request handler path.
- Long content attributes are externalized into `audit_artifacts`; persisted span attributes keep an
  artifact reference instead of a huge prompt, completion, or tool result.

Normal review generation uses the `audit_reviews.id` value as `audit.run_id`,
`audit.review_id`, and the persisted `audit_run_id`. Optimization runs that do not create
`audit_reviews` rows omit `review_id` and use `source="optimization"` with
`optimization_run_id`/`source_run_id`.

## Environment

- `OBSERVABILITY_ENABLED`: enable OpenTelemetry setup. Default: `true`.
- `OBSERVABILITY_CAPTURE_ALL`: persist non-audit spans too. Default: `false`.
- `OBSERVABILITY_LOCAL_EXPORT_ENABLED`: persist spans to the app database. Default: `true`.
- `OBSERVABILITY_OTLP_ENABLED`: also export spans to OTLP. Default: `false`.
- `OTEL_SERVICE_NAME`: service name resource attribute. Default: `tfr-assistant`.
- `APP_ENV`: deployment environment resource attribute. Default: `local`.
- `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT`: OTLP HTTP trace endpoint.
- `OTEL_EXPORTER_OTLP_ENDPOINT`: optional generic OTLP endpoint fallback.
- `PYDANTIC_AI_OTEL_INCLUDE_CONTENT`: include prompts, completions, and tool content in Pydantic AI
  telemetry. Default: `true` for local dev visibility.
- `PYDANTIC_AI_INCLUDE_BINARY_CONTENT`: include binary content. Default: `false`.
- `PYDANTIC_AI_INSTRUMENTATION_VERSION`: Pydantic AI GenAI format version. Default: `2`.
- `OBSERVABILITY_PERSIST_RAW_CONTENT`: store full artifact text. Default: `true`.
- `OBSERVABILITY_ARTIFACT_PREVIEW_CHARS`: preview length. Default: `1000`.
- `OBSERVABILITY_MAX_INLINE_ATTRIBUTE_CHARS`: max string length kept directly on span attributes.
  Default: `1000`.

## Pydantic AI

Pydantic AI can emit OpenTelemetry spans without Logfire by using `Agent.instrument_all(...)`.
The current Pydantic AI docs describe `InstrumentationSettings`, `include_content`,
`include_binary_content`, and versioned GenAI formats. Version 2 stores message content in
attributes such as `gen_ai.input.messages`, `gen_ai.output.messages`,
`gen_ai.system_instructions`, and `pydantic_ai.all_messages`; version 3+ moves tool call content
toward `gen_ai.tool.call.arguments` and `gen_ai.tool.call.result`.

The mapper is intentionally tolerant of these variants. OpenTelemetry trace parenting comes from
context propagation, while passing `usage=ctx.usage` to sub-agent runs is only for usage accounting.

Recommended sub-agent pattern:

```python
@main_agent.tool
async def analyze_coverage(ctx: RunContext[AuditDeps], claim_summary: str) -> str:
    span = trace.get_current_span()
    span.set_attribute("audit.delegates_to_agent", "coverage_sub_agent")

    result = await coverage_agent.run(
        f"Analyze coverage for this claim:\n{claim_summary}",
        deps=ctx.deps,
        usage=ctx.usage,
    )
    return result.output
```

## Search And UI

The backend exposes:

- `GET /api/observability/traces`
- `GET /api/observability/traces/{trace_id}`
- `GET /api/observability/traces/{trace_id}/tree`
- `GET /api/observability/traces/{trace_id}/artifacts`
- `GET /api/observability/spans`
- `GET /api/observability/delegations`

The Next.js page at `/observability` supports trace filtering, trace detail, nested span tree,
delegation visibility, selected span attributes, and preview-first artifact browsing with raw
content loaded on demand.

## SQLite And Postgres

SQLite is supported for local development through portable JSON columns and normal B-tree indexes.
For Postgres, the migration adds guarded JSONB GIN indexes, full-text search over artifact content,
common expression indexes, and a pg_trgm index only when the `pg_trgm` extension already exists.

Future tenant/auth scoping should be attached at the repository/API layer by requiring tenant/user
context and filtering traces, spans, and artifacts by the persisted `tenant_id` and `user_id`
columns.

## Operational Notes

For production, keep local persistence enabled only if this application is the intended trace
system of record. Otherwise enable OTLP export and place an OpenTelemetry Collector or ingestion
worker between the app and the production observability store.

For process boundaries such as queues or external workers, inject and extract W3C trace context.
Async in-process sub-agent calls inherit trace context automatically when they run inside
`observed_audit_generation()`.
