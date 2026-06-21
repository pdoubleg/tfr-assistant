from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import inspect, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import Settings
from app.db.models import (
    AuditAgentDelegationORM,
    AuditArtifactORM,
    AuditSpanORM,
    Base,
)
from app.observability.context import apply_context_to_span, audit_observation_context
from app.observability.repository import ObservabilityRepository, TraceSearch


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)
    async with session_factory() as db_session:
        yield db_session

    await engine.dispose()


@pytest.fixture
def observability_settings() -> Settings:
    return Settings(
        observability_artifact_preview_chars=24,
        observability_max_inline_attribute_chars=40,
        observability_persist_raw_content=True,
    )


def _span(
    *,
    span_id: str,
    parent_span_id: str | None,
    name: str,
    operation: str,
    attributes: dict[str, Any],
    started_at: datetime,
    duration_ms: int = 10,
    status_code: str = "OK",
    events: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "trace_id": "11111111111111111111111111111111",
        "span_id": span_id,
        "parent_span_id": parent_span_id,
        "name": name,
        "kind": "INTERNAL",
        "status_code": status_code,
        "started_at": started_at,
        "ended_at": started_at + timedelta(milliseconds=duration_ms),
        "duration_ms": duration_ms,
        "resource": {"service.name": "test"},
        "attributes": {
            "audit.observed": True,
            "audit.run_id": "review-1",
            "audit.review_id": "review-1",
            "audit.source": "eval",
            "audit.eval_run_id": "eval-1",
            "audit.claim_number": "CLM-123",
            "audit.form_id": "tfr_default",
            "audit.form_version": "v1",
            "gen_ai.operation.name": operation,
            **attributes,
        },
        "events": events or [],
    }


def _sample_spans() -> list[dict[str, Any]]:
    base = datetime(2026, 1, 1, 12, tzinfo=UTC)
    return [
        _span(
            span_id="0000000000000001",
            parent_span_id=None,
            name="invoke_agent audit_form_agent",
            operation="invoke_agent",
            attributes={
                "gen_ai.agent.name": "audit_form_agent",
                "pydantic_ai.all_messages": [{"role": "user", "content": "review claim"}],
            },
            started_at=base,
            duration_ms=100,
        ),
        _span(
            span_id="0000000000000002",
            parent_span_id="0000000000000001",
            name="execute_tool analyze_coverage",
            operation="execute_tool",
            attributes={
                "gen_ai.tool.name": "analyze_coverage",
                "audit.delegates_to_agent": "coverage_sub_agent",
                "tool_response": "coverage memo " * 20,
            },
            started_at=base + timedelta(milliseconds=5),
            duration_ms=40,
        ),
        _span(
            span_id="0000000000000003",
            parent_span_id="0000000000000002",
            name="invoke_agent coverage_sub_agent",
            operation="invoke_agent",
            attributes={"gen_ai.agent.name": "coverage_sub_agent"},
            started_at=base + timedelta(milliseconds=10),
            duration_ms=25,
        ),
        _span(
            span_id="0000000000000004",
            parent_span_id="0000000000000003",
            name="chat gpt-5.4-nano",
            operation="chat",
            attributes={
                "gen_ai.request.model": "gpt-5.4-nano",
                "gen_ai.system": "openai",
                "gen_ai.usage.input_tokens": 12,
                "gen_ai.usage.output_tokens": 8,
                "gen_ai.output.messages": [{"role": "assistant", "content": "answer"}],
            },
            started_at=base + timedelta(milliseconds=12),
            duration_ms=20,
        ),
    ]


@pytest.mark.anyio
async def test_observability_tables_create_under_sqlite() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
        table_names = await connection.run_sync(
            lambda sync_connection: set(inspect(sync_connection).get_table_names())
        )

    await engine.dispose()

    assert {
        "audit_traces",
        "audit_spans",
        "audit_span_events",
        "audit_artifacts",
        "audit_agent_delegations",
    } <= table_names


@pytest.mark.anyio
async def test_ingest_spans_is_idempotent_and_externalizes_artifacts(
    session,
    observability_settings: Settings,
) -> None:
    repository = ObservabilityRepository(session, observability_settings)

    await repository.ingest_spans(_sample_spans())
    await repository.ingest_spans(_sample_spans())

    spans = (await session.scalars(select(AuditSpanORM))).all()
    artifacts = (await session.scalars(select(AuditArtifactORM))).all()
    trace = await repository.get_trace("11111111111111111111111111111111")

    assert len(spans) == 4
    assert len(artifacts) == 3
    assert trace.audit_run_id == "review-1"
    assert trace.review_id == "review-1"
    assert trace.source == "eval"
    assert trace.claim_number == "CLM-123"
    assert trace.span_count == 4
    assert trace.total_tokens == 20
    assert trace.agent_names_json == ["audit_form_agent", "coverage_sub_agent"]
    assert trace.model_names_json == ["gpt-5.4-nano"]
    assert artifacts[0].content_text is not None
    assert len(artifacts[0].content_preview) <= 24
    assert len(artifacts[0].content_sha256) == 64


@pytest.mark.anyio
async def test_trace_tree_search_filters_and_delegation_derivation(
    session,
    observability_settings: Settings,
) -> None:
    repository = ObservabilityRepository(session, observability_settings)
    await repository.ingest_spans(_sample_spans())

    total, traces = await repository.search_traces(
        TraceSearch(
            claim_number="CLM-123",
            source="eval, synthetic",
            agent_name="coverage_sub_agent, missing_agent",
            text_query="coverage memo",
        )
    )
    tree = await repository.trace_tree("11111111111111111111111111111111")
    delegations = (await session.scalars(select(AuditAgentDelegationORM))).all()

    assert total == 1
    assert traces[0].trace_id == "11111111111111111111111111111111"
    assert tree[0]["span"].span_id == "0000000000000001"
    assert tree[0]["children"][0]["span"].span_id == "0000000000000002"
    assert delegations[0].parent_span_id == "0000000000000002"
    assert delegations[0].child_span_id == "0000000000000003"
    assert delegations[0].child_agent_name == "coverage_sub_agent"


@pytest.mark.anyio
async def test_trace_search_matches_child_claims_in_shared_trace(
    session,
    observability_settings: Settings,
) -> None:
    repository = ObservabilityRepository(session, observability_settings)
    spans = _sample_spans()
    spans.append(
        _span(
            span_id="0000000000000005",
            parent_span_id=None,
            name="invoke_agent audit_form_agent",
            operation="invoke_agent",
            attributes={
                "audit.run_id": "review-2",
                "audit.review_id": "review-2",
                "audit.claim_number": "CLM-456",
                "gen_ai.agent.name": "audit_form_agent",
                "tool_response": "second claim memo " * 20,
            },
            started_at=datetime(2026, 1, 1, 12, 1, tzinfo=UTC),
            duration_ms=50,
        )
    )

    await repository.ingest_spans(spans)

    total, traces = await repository.search_traces(TraceSearch(claim_number="456"))
    assert total == 1
    assert traces[0].trace_id == "11111111111111111111111111111111"

    total, traces = await repository.search_traces(TraceSearch(audit_run_id="review-2"))
    assert total == 1
    assert traces[0].trace_id == "11111111111111111111111111111111"


@pytest.mark.anyio
async def test_error_rollup_and_span_events(session, observability_settings: Settings) -> None:
    spans = _sample_spans()
    spans[-1]["status_code"] = "ERROR"
    spans[-1]["events"] = [
        {
            "event_index": 0,
            "name": "exception",
            "timestamp": datetime(2026, 1, 1, 12, tzinfo=UTC),
            "attributes": {
                "exception.type": "RuntimeError",
                "exception.message": "model failed",
            },
        }
    ]
    repository = ObservabilityRepository(session, observability_settings)

    await repository.ingest_spans(spans)
    trace = await repository.get_trace("11111111111111111111111111111111")
    events = await repository.list_events(trace.trace_id)

    assert trace.status_code == "ERROR"
    assert trace.error_count == 1
    assert trace.error_type == "RuntimeError"
    assert events[0].exception_message == "model failed"


def test_audit_context_stamps_current_span_attributes() -> None:
    class FakeSpan:
        def __init__(self) -> None:
            self.attributes: dict[str, Any] = {}

        def set_attribute(self, key: str, value: Any) -> None:
            self.attributes[key] = value

    span = FakeSpan()
    with audit_observation_context(
        audit_run_id="review-1",
        source="batch",
        claim_number="CLM-123",
    ):
        apply_context_to_span(span)

    assert span.attributes["audit.observed"] is True
    assert span.attributes["audit.run_id"] == "review-1"
    assert span.attributes["audit.source"] == "batch"
    assert span.attributes["audit.claim_number"] == "CLM-123"
