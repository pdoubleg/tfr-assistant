from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class AuditTraceRecord(BaseModel):
    trace_id: str
    audit_run_id: str | None = None
    review_id: str | None = None
    source: str = ""
    source_run_id: str | None = None
    batch_id: str | None = None
    eval_run_id: str | None = None
    eval_dataset_id: str | None = None
    optimization_run_id: str | None = None
    case_id: str | None = None
    claim_number: str = ""
    form_id: str = ""
    form_version: str = ""
    form_kind: str = ""
    status_code: str = "UNSET"
    error_type: str | None = None
    span_count: int = 0
    error_count: int = 0
    started_at: datetime | None = None
    ended_at: datetime | None = None
    duration_ms: int | None = None
    agent_names: list[str] = Field(default_factory=list)
    model_names: list[str] = Field(default_factory=list)
    tool_names: list[str] = Field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    estimated_cost_usd: float | None = None
    created_at: datetime
    updated_at: datetime


class AuditTraceListResponse(BaseModel):
    total: int
    limit: int
    offset: int
    traces: list[AuditTraceRecord]


class AuditObservabilityFacets(BaseModel):
    sources: list[str] = Field(default_factory=list)
    agent_names: list[str] = Field(default_factory=list)
    model_names: list[str] = Field(default_factory=list)
    status_codes: list[str] = Field(default_factory=list)


class AuditSpanRecord(BaseModel):
    trace_id: str
    span_id: str
    parent_span_id: str | None = None
    name: str
    kind: str = ""
    span_type: str = ""
    status_code: str = "UNSET"
    error_type: str | None = None
    error_message: str | None = None
    agent_name: str = ""
    model_name: str = ""
    provider_name: str = ""
    tool_name: str = ""
    source: str = ""
    audit_run_id: str | None = None
    review_id: str | None = None
    batch_id: str | None = None
    eval_run_id: str | None = None
    optimization_run_id: str | None = None
    case_id: str | None = None
    claim_number: str = ""
    started_at: datetime | None = None
    ended_at: datetime | None = None
    duration_ms: int | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    estimated_cost_usd: float | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)


class AuditSpanEventRecord(BaseModel):
    trace_id: str
    span_id: str
    event_index: int
    name: str
    event_time: datetime | None = None
    exception_type: str | None = None
    exception_message: str | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)


class AuditArtifactRecord(BaseModel):
    id: str
    trace_id: str
    span_id: str | None = None
    audit_run_id: str | None = None
    review_id: str | None = None
    source: str = ""
    source_run_id: str | None = None
    claim_number: str = ""
    artifact_type: str
    artifact_key: str
    name: str
    content_format: str
    content_preview: str
    content_text: str | None = None
    content_sha256: str
    content_size: int
    redaction_state: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class AuditAgentDelegationRecord(BaseModel):
    trace_id: str
    parent_span_id: str | None = None
    child_span_id: str
    parent_agent_name: str = ""
    child_agent_name: str = ""
    tool_name: str = ""
    confidence: float = 0.0
    attributes: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class AuditTraceTreeNode(BaseModel):
    span: AuditSpanRecord
    children: list[AuditTraceTreeNode] = Field(default_factory=list)


class AuditTraceDetail(BaseModel):
    trace: AuditTraceRecord
    spans: list[AuditSpanRecord]
    events: list[AuditSpanEventRecord]
    delegations: list[AuditAgentDelegationRecord]
