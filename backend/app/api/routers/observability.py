from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    AuditAgentDelegationORM,
    AuditArtifactORM,
    AuditSpanEventORM,
    AuditSpanORM,
    AuditTraceORM,
)
from app.db.session import get_session
from app.observability.repository import ObservabilityRepository, TraceSearch
from app.schemas.observability import (
    AuditAgentDelegationRecord,
    AuditArtifactRecord,
    AuditObservabilityFacets,
    AuditSpanEventRecord,
    AuditSpanRecord,
    AuditTraceDetail,
    AuditTraceListResponse,
    AuditTraceRecord,
    AuditTraceTreeNode,
)

router = APIRouter()


async def _distinct_non_empty(session: AsyncSession, column) -> list[str]:
    values = (
        await session.scalars(
            select(column).where(column.is_not(None), column != "").distinct().order_by(column)
        )
    ).all()
    return [str(value) for value in values if str(value).strip()]


def _trace_to_schema(trace: AuditTraceORM) -> AuditTraceRecord:
    return AuditTraceRecord(
        trace_id=trace.trace_id,
        audit_run_id=trace.audit_run_id,
        review_id=trace.review_id,
        source=trace.source,
        source_run_id=trace.source_run_id,
        batch_id=trace.batch_id,
        eval_run_id=trace.eval_run_id,
        eval_dataset_id=trace.eval_dataset_id,
        optimization_run_id=trace.optimization_run_id,
        case_id=trace.case_id,
        claim_number=trace.claim_number,
        form_id=trace.form_id,
        form_version=trace.form_version,
        form_kind=trace.form_kind,
        status_code=trace.status_code,
        error_type=trace.error_type,
        span_count=trace.span_count,
        error_count=trace.error_count,
        started_at=trace.started_at,
        ended_at=trace.ended_at,
        duration_ms=trace.duration_ms,
        agent_names=trace.agent_names_json,
        model_names=trace.model_names_json,
        tool_names=trace.tool_names_json,
        input_tokens=trace.input_tokens,
        output_tokens=trace.output_tokens,
        total_tokens=trace.total_tokens,
        estimated_cost_usd=trace.estimated_cost_usd,
        created_at=trace.created_at,
        updated_at=trace.updated_at,
    )


def _span_to_schema(span: AuditSpanORM) -> AuditSpanRecord:
    return AuditSpanRecord(
        trace_id=span.trace_id,
        span_id=span.span_id,
        parent_span_id=span.parent_span_id,
        name=span.name,
        kind=span.kind,
        span_type=span.span_type,
        status_code=span.status_code,
        error_type=span.error_type,
        error_message=span.error_message,
        agent_name=span.agent_name,
        model_name=span.model_name,
        provider_name=span.provider_name,
        tool_name=span.tool_name,
        source=span.source,
        audit_run_id=span.audit_run_id,
        review_id=span.review_id,
        batch_id=span.batch_id,
        eval_run_id=span.eval_run_id,
        optimization_run_id=span.optimization_run_id,
        case_id=span.case_id,
        claim_number=span.claim_number,
        started_at=span.started_at,
        ended_at=span.ended_at,
        duration_ms=span.duration_ms,
        input_tokens=span.input_tokens,
        output_tokens=span.output_tokens,
        total_tokens=span.total_tokens,
        estimated_cost_usd=span.estimated_cost_usd,
        attributes=span.attributes_json or {},
    )


def _event_to_schema(event: AuditSpanEventORM) -> AuditSpanEventRecord:
    return AuditSpanEventRecord(
        trace_id=event.trace_id,
        span_id=event.span_id,
        event_index=event.event_index,
        name=event.name,
        event_time=event.event_time,
        exception_type=event.exception_type,
        exception_message=event.exception_message,
        attributes=event.attributes_json or {},
    )


def _artifact_to_schema(
    artifact: AuditArtifactORM,
    *,
    include_content: bool,
) -> AuditArtifactRecord:
    return AuditArtifactRecord(
        id=artifact.id,
        trace_id=artifact.trace_id,
        span_id=artifact.span_id,
        audit_run_id=artifact.audit_run_id,
        review_id=artifact.review_id,
        source=artifact.source,
        source_run_id=artifact.source_run_id,
        claim_number=artifact.claim_number,
        artifact_type=artifact.artifact_type,
        artifact_key=artifact.artifact_key,
        name=artifact.name,
        content_format=artifact.content_format,
        content_preview=artifact.content_preview,
        content_text=artifact.content_text if include_content else None,
        content_sha256=artifact.content_sha256,
        content_size=artifact.content_size,
        redaction_state=artifact.redaction_state,
        metadata=artifact.metadata_json or {},
        created_at=artifact.created_at,
    )


def _delegation_to_schema(delegation: AuditAgentDelegationORM) -> AuditAgentDelegationRecord:
    return AuditAgentDelegationRecord(
        trace_id=delegation.trace_id,
        parent_span_id=delegation.parent_span_id,
        child_span_id=delegation.child_span_id,
        parent_agent_name=delegation.parent_agent_name,
        child_agent_name=delegation.child_agent_name,
        tool_name=delegation.tool_name,
        confidence=delegation.confidence,
        attributes=delegation.attributes_json or {},
        created_at=delegation.created_at,
    )


def _tree_to_schema(node: dict) -> AuditTraceTreeNode:
    return AuditTraceTreeNode(
        span=_span_to_schema(node["span"]),
        children=[_tree_to_schema(child) for child in node["children"]],
    )


def _trace_search(
    *,
    claim_number: str = "",
    audit_run_id: str = "",
    source: str = "",
    source_run_id: str = "",
    batch_id: str = "",
    eval_run_id: str = "",
    optimization_run_id: str = "",
    case_id: str = "",
    agent_name: str = "",
    model_name: str = "",
    provider_name: str = "",
    tool_name: str = "",
    span_type: str = "",
    status_code: str = "",
    error_type: str = "",
    started_at_from: datetime | None = None,
    started_at_to: datetime | None = None,
    text_query: str = "",
    limit: int = 50,
    offset: int = 0,
) -> TraceSearch:
    return TraceSearch(
        claim_number=claim_number,
        audit_run_id=audit_run_id,
        source=source,
        source_run_id=source_run_id,
        batch_id=batch_id,
        eval_run_id=eval_run_id,
        optimization_run_id=optimization_run_id,
        case_id=case_id,
        agent_name=agent_name,
        model_name=model_name,
        provider_name=provider_name,
        tool_name=tool_name,
        span_type=span_type,
        status_code=status_code,
        error_type=error_type,
        started_at_from=started_at_from,
        started_at_to=started_at_to,
        text_query=text_query,
        limit=limit,
        offset=offset,
    )


@router.get("/facets", response_model=AuditObservabilityFacets)
async def get_facets(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AuditObservabilityFacets:
    trace_sources = await _distinct_non_empty(session, AuditTraceORM.source)
    span_sources = await _distinct_non_empty(session, AuditSpanORM.source)
    trace_statuses = await _distinct_non_empty(session, AuditTraceORM.status_code)
    span_statuses = await _distinct_non_empty(session, AuditSpanORM.status_code)
    return AuditObservabilityFacets(
        sources=sorted({*trace_sources, *span_sources}),
        agent_names=await _distinct_non_empty(session, AuditSpanORM.agent_name),
        model_names=await _distinct_non_empty(session, AuditSpanORM.model_name),
        status_codes=sorted({*trace_statuses, *span_statuses}),
    )


@router.get("/traces", response_model=AuditTraceListResponse)
async def list_traces(
    session: Annotated[AsyncSession, Depends(get_session)],
    claim_number: Annotated[str, Query()] = "",
    audit_run_id: Annotated[str, Query()] = "",
    source: Annotated[str, Query()] = "",
    source_run_id: Annotated[str, Query()] = "",
    batch_id: Annotated[str, Query()] = "",
    eval_run_id: Annotated[str, Query()] = "",
    optimization_run_id: Annotated[str, Query()] = "",
    case_id: Annotated[str, Query()] = "",
    agent_name: Annotated[str, Query()] = "",
    model_name: Annotated[str, Query()] = "",
    provider_name: Annotated[str, Query()] = "",
    tool_name: Annotated[str, Query()] = "",
    span_type: Annotated[str, Query()] = "",
    status_code: Annotated[str, Query()] = "",
    error_type: Annotated[str, Query()] = "",
    started_at_from: Annotated[datetime | None, Query()] = None,
    started_at_to: Annotated[datetime | None, Query()] = None,
    text_query: Annotated[str, Query()] = "",
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> AuditTraceListResponse:
    search = _trace_search(
        claim_number=claim_number,
        audit_run_id=audit_run_id,
        source=source,
        source_run_id=source_run_id,
        batch_id=batch_id,
        eval_run_id=eval_run_id,
        optimization_run_id=optimization_run_id,
        case_id=case_id,
        agent_name=agent_name,
        model_name=model_name,
        provider_name=provider_name,
        tool_name=tool_name,
        span_type=span_type,
        status_code=status_code,
        error_type=error_type,
        started_at_from=started_at_from,
        started_at_to=started_at_to,
        text_query=text_query,
        limit=limit,
        offset=offset,
    )
    total, traces = await ObservabilityRepository(session).search_traces(search)
    return AuditTraceListResponse(
        total=total,
        limit=limit,
        offset=offset,
        traces=[_trace_to_schema(trace) for trace in traces],
    )


@router.get("/traces/{trace_id}", response_model=AuditTraceDetail)
async def get_trace(
    trace_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AuditTraceDetail:
    repository = ObservabilityRepository(session)
    try:
        trace = await repository.get_trace(trace_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return AuditTraceDetail(
        trace=_trace_to_schema(trace),
        spans=[_span_to_schema(span) for span in await repository.list_spans(trace_id=trace_id)],
        events=[_event_to_schema(event) for event in await repository.list_events(trace_id)],
        delegations=[
            _delegation_to_schema(delegation)
            for delegation in await repository.list_delegations(trace_id)
        ],
    )


@router.get("/traces/{trace_id}/tree", response_model=list[AuditTraceTreeNode])
async def get_trace_tree(
    trace_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[AuditTraceTreeNode]:
    repository = ObservabilityRepository(session)
    try:
        await repository.get_trace(trace_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return [_tree_to_schema(node) for node in await repository.trace_tree(trace_id)]


@router.get("/traces/{trace_id}/artifacts", response_model=list[AuditArtifactRecord])
async def list_trace_artifacts(
    trace_id: str,
    session: Annotated[AsyncSession, Depends(get_session)],
    span_id: Annotated[str, Query()] = "",
    artifact_type: Annotated[str, Query()] = "",
    include_content: Annotated[bool, Query()] = False,
) -> list[AuditArtifactRecord]:
    repository = ObservabilityRepository(session)
    try:
        await repository.get_trace(trace_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    artifacts = await repository.list_artifacts(
        trace_id=trace_id,
        span_id=span_id or None,
        artifact_type=artifact_type,
    )
    return [
        _artifact_to_schema(artifact, include_content=include_content) for artifact in artifacts
    ]


@router.get("/spans", response_model=list[AuditSpanRecord])
async def list_spans(
    session: Annotated[AsyncSession, Depends(get_session)],
    trace_id: Annotated[str, Query()] = "",
    claim_number: Annotated[str, Query()] = "",
    audit_run_id: Annotated[str, Query()] = "",
    source: Annotated[str, Query()] = "",
    source_run_id: Annotated[str, Query()] = "",
    batch_id: Annotated[str, Query()] = "",
    eval_run_id: Annotated[str, Query()] = "",
    optimization_run_id: Annotated[str, Query()] = "",
    case_id: Annotated[str, Query()] = "",
    agent_name: Annotated[str, Query()] = "",
    model_name: Annotated[str, Query()] = "",
    provider_name: Annotated[str, Query()] = "",
    tool_name: Annotated[str, Query()] = "",
    span_type: Annotated[str, Query()] = "",
    status_code: Annotated[str, Query()] = "",
    error_type: Annotated[str, Query()] = "",
    started_at_from: Annotated[datetime | None, Query()] = None,
    started_at_to: Annotated[datetime | None, Query()] = None,
) -> list[AuditSpanRecord]:
    search = _trace_search(
        claim_number=claim_number,
        audit_run_id=audit_run_id,
        source=source,
        source_run_id=source_run_id,
        batch_id=batch_id,
        eval_run_id=eval_run_id,
        optimization_run_id=optimization_run_id,
        case_id=case_id,
        agent_name=agent_name,
        model_name=model_name,
        provider_name=provider_name,
        tool_name=tool_name,
        span_type=span_type,
        status_code=status_code,
        error_type=error_type,
        started_at_from=started_at_from,
        started_at_to=started_at_to,
    )
    spans = await ObservabilityRepository(session).list_spans(
        trace_id=trace_id or None,
        search=search,
    )
    return [_span_to_schema(span) for span in spans]


@router.get("/delegations", response_model=list[AuditAgentDelegationRecord])
async def list_delegations(
    session: Annotated[AsyncSession, Depends(get_session)],
    trace_id: Annotated[str, Query()] = "",
) -> list[AuditAgentDelegationRecord]:
    delegations = await ObservabilityRepository(session).list_delegations(trace_id or None)
    return [_delegation_to_schema(delegation) for delegation in delegations]
