from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.db.models import (
    AuditAgentDelegationORM,
    AuditArtifactORM,
    AuditSpanEventORM,
    AuditSpanORM,
    AuditTraceORM,
    utc_now,
)
from app.observability.artifacts import (
    ArtifactCandidate,
    extract_artifacts_from_attributes,
    preview_text,
)
from app.observability.spans import (
    extract_audit_columns,
    extract_span_columns,
    json_safe,
    should_persist_span,
)


@dataclass(slots=True)
class TraceSearch:
    claim_number: str = ""
    audit_run_id: str = ""
    source: str = ""
    source_run_id: str = ""
    batch_id: str = ""
    eval_run_id: str = ""
    optimization_run_id: str = ""
    case_id: str = ""
    agent_name: str = ""
    model_name: str = ""
    provider_name: str = ""
    tool_name: str = ""
    span_type: str = ""
    status_code: str = ""
    error_type: str = ""
    started_at_from: datetime | None = None
    started_at_to: datetime | None = None
    text_query: str = ""
    limit: int = 50
    offset: int = 0


def _clean_str(value: Any) -> str:
    return str(value or "").strip()


def _first_non_empty(*values: Any) -> Any:
    for value in values:
        if value is not None and value != "":
            return value
    return None


def _split_filter(value: str) -> list[str]:
    return [part.strip() for part in str(value or "").split(",") if part.strip()]


def _column_filter(column: Any, values: list[str], *, partial: bool = False) -> Any:
    if partial:
        return or_(*(column.ilike(f"%{value}%") for value in values))
    if len(values) == 1:
        return column == values[0]
    return column.in_(values)


def _update_if_empty(record: object, **values: Any) -> None:
    for key, value in values.items():
        if value is None or value == "":
            continue
        if not getattr(record, key, None):
            setattr(record, key, value)


def _artifact_preview(candidate: ArtifactCandidate, settings: Settings) -> str:
    return preview_text(candidate.content_text, settings.observability_artifact_preview_chars)


class ObservabilityRepository:
    def __init__(self, session: AsyncSession, settings: Settings | None = None) -> None:
        self.session = session
        self.settings = settings or get_settings()

    async def ingest_spans(self, spans: Iterable[dict[str, Any]]) -> None:
        trace_ids: set[str] = set()
        for span in spans:
            if not should_persist_span(span, capture_all=self.settings.observability_capture_all):
                continue
            trace_id = _clean_str(span.get("trace_id"))
            span_id = _clean_str(span.get("span_id"))
            if not trace_id or not span_id:
                continue

            original_attributes = dict(span.get("attributes") or {})
            audit_columns = extract_audit_columns(original_attributes)
            sanitized_attributes, artifacts = extract_artifacts_from_attributes(
                original_attributes,
                self.settings,
            )
            sanitized_span = {**span, "attributes": sanitized_attributes}
            span_columns = extract_span_columns({**span, "attributes": original_attributes})
            await self._upsert_trace(trace_id, audit_columns, sanitized_attributes)
            await self._upsert_span(sanitized_span, audit_columns, span_columns)
            await self._upsert_events(trace_id, span_id, span.get("events") or [])
            await self._upsert_artifacts(trace_id, span_id, audit_columns, artifacts)
            trace_ids.add(trace_id)

        if trace_ids:
            await self.session.flush()

        for trace_id in trace_ids:
            await self.refresh_trace_rollup(trace_id)
        await self.session.commit()

    async def persist_artifact(
        self,
        *,
        trace_id: str,
        span_id: str | None,
        candidate: ArtifactCandidate,
        audit_columns: dict[str, Any] | None = None,
    ) -> AuditArtifactORM:
        audit_columns = audit_columns or {}
        artifact = await self._upsert_artifact(trace_id, span_id, audit_columns, candidate)
        await self.session.commit()
        return artifact

    async def search_traces(self, search: TraceSearch) -> tuple[int, list[AuditTraceORM]]:
        statement = select(AuditTraceORM)
        statement = self._apply_trace_filters(statement, search)
        count_statement = select(func.count()).select_from(statement.subquery())
        total = await self.session.scalar(count_statement) or 0
        statement = (
            statement.order_by(
                func.coalesce(AuditTraceORM.started_at, AuditTraceORM.created_at).desc(),
                AuditTraceORM.created_at.desc(),
            )
            .offset(max(search.offset, 0))
            .limit(max(1, min(search.limit, 200)))
        )
        return total, (await self.session.scalars(statement)).all()

    async def get_trace(self, trace_id: str) -> AuditTraceORM:
        trace = await self.session.scalar(
            select(AuditTraceORM).where(AuditTraceORM.trace_id == trace_id)
        )
        if trace is None:
            raise KeyError(f"Unknown trace: {trace_id}")
        return trace

    async def list_spans(
        self,
        *,
        trace_id: str | None = None,
        search: TraceSearch | None = None,
    ) -> list[AuditSpanORM]:
        statement = select(AuditSpanORM)
        if trace_id:
            statement = statement.where(AuditSpanORM.trace_id == trace_id)
        if search:
            statement = self._apply_span_filters(statement, search)
        statement = statement.order_by(AuditSpanORM.started_at.asc(), AuditSpanORM.name.asc())
        return (await self.session.scalars(statement)).all()

    async def list_events(self, trace_id: str) -> list[AuditSpanEventORM]:
        return (
            await self.session.scalars(
                select(AuditSpanEventORM)
                .where(AuditSpanEventORM.trace_id == trace_id)
                .order_by(AuditSpanEventORM.span_id.asc(), AuditSpanEventORM.event_index.asc())
            )
        ).all()

    async def list_artifacts(
        self,
        *,
        trace_id: str,
        span_id: str | None = None,
        artifact_type: str = "",
    ) -> list[AuditArtifactORM]:
        statement = select(AuditArtifactORM).where(AuditArtifactORM.trace_id == trace_id)
        if span_id:
            statement = statement.where(AuditArtifactORM.span_id == span_id)
        if artifact_type:
            statement = statement.where(AuditArtifactORM.artifact_type == artifact_type)
        statement = statement.order_by(AuditArtifactORM.created_at.asc())
        return (await self.session.scalars(statement)).all()

    async def list_delegations(self, trace_id: str | None = None) -> list[AuditAgentDelegationORM]:
        statement = select(AuditAgentDelegationORM)
        if trace_id:
            statement = statement.where(AuditAgentDelegationORM.trace_id == trace_id)
        statement = statement.order_by(AuditAgentDelegationORM.created_at.asc())
        return (await self.session.scalars(statement)).all()

    async def trace_tree(self, trace_id: str) -> list[dict[str, Any]]:
        spans = await self.list_spans(trace_id=trace_id)
        nodes = [
            {
                "span": span,
                "children": [],
            }
            for span in spans
        ]
        by_id = {node["span"].span_id: node for node in nodes}
        roots: list[dict[str, Any]] = []
        for node in nodes:
            parent_id = node["span"].parent_span_id
            parent = by_id.get(parent_id or "")
            if parent is None:
                roots.append(node)
            else:
                parent["children"].append(node)
        return roots

    async def refresh_trace_rollup(self, trace_id: str) -> None:
        trace = await self.get_trace(trace_id)
        spans = await self.list_spans(trace_id=trace_id)
        if not spans:
            return

        started_values = [span.started_at for span in spans if span.started_at is not None]
        ended_values = [span.ended_at for span in spans if span.ended_at is not None]
        started_at = min(started_values) if started_values else None
        ended_at = max(ended_values) if ended_values else None
        duration_ms = None
        if started_at and ended_at:
            duration_ms = int(max(0, (ended_at - started_at).total_seconds() * 1000))

        error_spans = [span for span in spans if span.status_code == "ERROR" or span.error_type]
        usage_spans = [span for span in spans if span.span_type == "model"]
        if not usage_spans:
            usage_spans = spans

        trace.span_count = len(spans)
        trace.error_count = len(error_spans)
        trace.started_at = started_at
        trace.ended_at = ended_at
        trace.duration_ms = duration_ms
        trace.status_code = "ERROR" if error_spans else "OK"
        trace.error_type = next((span.error_type for span in error_spans if span.error_type), None)
        trace.agent_names_json = sorted({span.agent_name for span in spans if span.agent_name})
        trace.model_names_json = sorted({span.model_name for span in spans if span.model_name})
        trace.tool_names_json = sorted({span.tool_name for span in spans if span.tool_name})
        trace.input_tokens = sum(span.input_tokens or 0 for span in usage_spans)
        trace.output_tokens = sum(span.output_tokens or 0 for span in usage_spans)
        trace.total_tokens = sum(span.total_tokens or 0 for span in usage_spans)
        costs = [span.estimated_cost_usd for span in usage_spans if span.estimated_cost_usd]
        trace.estimated_cost_usd = sum(costs) if costs else None

        representative = next((span for span in spans if span.audit_run_id), spans[0])
        _update_if_empty(
            trace,
            audit_run_id=representative.audit_run_id,
            review_id=representative.review_id,
            source=representative.source,
            source_run_id=representative.source_run_id,
            batch_id=representative.batch_id,
            eval_run_id=representative.eval_run_id,
            eval_dataset_id=representative.eval_dataset_id,
            optimization_run_id=representative.optimization_run_id,
            case_id=representative.case_id,
            claim_number=representative.claim_number,
            form_id=representative.form_id,
            form_version=representative.form_version,
            form_kind=representative.form_kind,
            tenant_id=representative.tenant_id,
            user_id=representative.user_id,
        )
        trace.updated_at = utc_now()
        await self._derive_delegations(trace_id, spans)

    async def _upsert_trace(
        self,
        trace_id: str,
        audit_columns: dict[str, Any],
        attributes: dict[str, Any],
    ) -> AuditTraceORM:
        trace = await self.session.scalar(
            select(AuditTraceORM).where(AuditTraceORM.trace_id == trace_id)
        )
        if trace is None:
            trace = AuditTraceORM(
                id=str(uuid4()),
                trace_id=trace_id,
                attributes_json={},
                agent_names_json=[],
                model_names_json=[],
                tool_names_json=[],
                source="",
                claim_number="",
                form_id="",
                form_version="",
                form_kind="",
            )
            self.session.add(trace)
            await self.session.flush()
        _update_if_empty(trace, **audit_columns)
        trace.attributes_json = {**(trace.attributes_json or {}), **attributes}
        trace.updated_at = utc_now()
        return trace

    async def _upsert_span(
        self,
        span: dict[str, Any],
        audit_columns: dict[str, Any],
        span_columns: dict[str, Any],
    ) -> AuditSpanORM:
        trace_id = span["trace_id"]
        span_id = span["span_id"]
        record = await self.session.scalar(
            select(AuditSpanORM).where(
                AuditSpanORM.trace_id == trace_id,
                AuditSpanORM.span_id == span_id,
            )
        )
        values = {
            "parent_span_id": span.get("parent_span_id"),
            "name": span.get("name") or "",
            "kind": span.get("kind") or "",
            "status_code": span.get("status_code") or "UNSET",
            "started_at": span.get("started_at"),
            "ended_at": span.get("ended_at"),
            "duration_ms": span.get("duration_ms"),
            "attributes_json": span.get("attributes") or {},
            "resource_json": span.get("resource") or {},
            "raw_span_json": {
                key: json_safe(value) for key, value in span.items() if key not in {"events"}
            },
            **audit_columns,
            **span_columns,
        }
        values["source"] = values.get("source") or ""
        values["claim_number"] = values.get("claim_number") or ""
        values["form_id"] = values.get("form_id") or ""
        values["form_version"] = values.get("form_version") or ""
        values["form_kind"] = values.get("form_kind") or ""
        if record is None:
            record = AuditSpanORM(
                id=str(uuid4()),
                trace_id=trace_id,
                span_id=span_id,
                **values,
            )
            self.session.add(record)
        else:
            for key, value in values.items():
                setattr(record, key, value)
            record.updated_at = utc_now()
        return record

    async def _upsert_events(
        self,
        trace_id: str,
        span_id: str,
        events: list[dict[str, Any]],
    ) -> None:
        for event in events:
            event_index = int(event.get("event_index") or 0)
            attributes = event.get("attributes") or {}
            record = await self.session.scalar(
                select(AuditSpanEventORM).where(
                    AuditSpanEventORM.trace_id == trace_id,
                    AuditSpanEventORM.span_id == span_id,
                    AuditSpanEventORM.event_index == event_index,
                )
            )
            values = {
                "name": event.get("name") or "",
                "event_time": event.get("timestamp"),
                "exception_type": _first_non_empty(attributes.get("exception.type")),
                "exception_message": _first_non_empty(attributes.get("exception.message")),
                "attributes_json": json_safe(attributes),
                "raw_event_json": json_safe(event),
            }
            if record is None:
                self.session.add(
                    AuditSpanEventORM(
                        id=str(uuid4()),
                        trace_id=trace_id,
                        span_id=span_id,
                        event_index=event_index,
                        **values,
                    )
                )
            else:
                for key, value in values.items():
                    setattr(record, key, value)

    async def _upsert_artifacts(
        self,
        trace_id: str,
        span_id: str,
        audit_columns: dict[str, Any],
        artifacts: list[ArtifactCandidate],
    ) -> None:
        for candidate in artifacts:
            await self._upsert_artifact(trace_id, span_id, audit_columns, candidate)

    async def _upsert_artifact(
        self,
        trace_id: str,
        span_id: str | None,
        audit_columns: dict[str, Any],
        candidate: ArtifactCandidate,
    ) -> AuditArtifactORM:
        content_hash = candidate.content_sha256
        record = await self.session.scalar(
            select(AuditArtifactORM).where(
                AuditArtifactORM.trace_id == trace_id,
                AuditArtifactORM.span_id == span_id,
                AuditArtifactORM.artifact_key == candidate.artifact_key,
                AuditArtifactORM.content_sha256 == content_hash,
            )
        )
        content_text = (
            candidate.content_text if self.settings.observability_persist_raw_content else None
        )
        redaction_state = "raw" if content_text is not None else "redacted"
        values = {
            "audit_run_id": audit_columns.get("audit_run_id"),
            "review_id": audit_columns.get("review_id"),
            "source": audit_columns.get("source") or "",
            "source_run_id": audit_columns.get("source_run_id"),
            "batch_id": audit_columns.get("batch_id"),
            "eval_run_id": audit_columns.get("eval_run_id"),
            "optimization_run_id": audit_columns.get("optimization_run_id"),
            "case_id": audit_columns.get("case_id"),
            "claim_number": audit_columns.get("claim_number") or "",
            "artifact_type": candidate.artifact_type,
            "artifact_key": candidate.artifact_key,
            "name": candidate.name,
            "content_format": candidate.content_format,
            "content_preview": _artifact_preview(candidate, self.settings),
            "content_text": content_text,
            "content_sha256": content_hash,
            "content_size": candidate.content_size,
            "redaction_state": redaction_state,
            "metadata_json": candidate.metadata,
        }
        if record is None:
            record = AuditArtifactORM(
                id=str(uuid4()),
                trace_id=trace_id,
                span_id=span_id,
                **values,
            )
            self.session.add(record)
        else:
            for key, value in values.items():
                setattr(record, key, value)
        return record

    async def _derive_delegations(self, trace_id: str, spans: list[AuditSpanORM]) -> None:
        await self.session.execute(
            delete(AuditAgentDelegationORM).where(AuditAgentDelegationORM.trace_id == trace_id)
        )
        by_id = {span.span_id: span for span in spans}
        children_by_parent: dict[str | None, list[AuditSpanORM]] = {}
        for span in spans:
            children_by_parent.setdefault(span.parent_span_id, []).append(span)

        for child in spans:
            if child.span_type != "agent":
                continue
            parent = by_id.get(child.parent_span_id or "")
            if parent and parent.span_type == "tool":
                self.session.add(
                    AuditAgentDelegationORM(
                        id=str(uuid4()),
                        trace_id=trace_id,
                        parent_span_id=parent.span_id,
                        child_span_id=child.span_id,
                        parent_agent_name=self._nearest_parent_agent(parent, by_id),
                        child_agent_name=child.agent_name or child.name,
                        tool_name=parent.tool_name or parent.name,
                        confidence=0.95,
                        attributes_json={"derived_from": "tool_parent"},
                    )
                )
                continue

            if parent:
                delegated_to = (parent.attributes_json or {}).get("audit.delegates_to_agent")
                if delegated_to and str(delegated_to) in {child.agent_name, child.name}:
                    self.session.add(
                        AuditAgentDelegationORM(
                            id=str(uuid4()),
                            trace_id=trace_id,
                            parent_span_id=parent.span_id,
                            child_span_id=child.span_id,
                            parent_agent_name=self._nearest_parent_agent(parent, by_id),
                            child_agent_name=child.agent_name or child.name,
                            tool_name=parent.tool_name or parent.name,
                            confidence=0.8,
                            attributes_json={"derived_from": "audit.delegates_to_agent"},
                        )
                    )

    def _nearest_parent_agent(
        self,
        span: AuditSpanORM,
        by_id: dict[str, AuditSpanORM],
    ) -> str:
        current = span
        while current.parent_span_id:
            parent = by_id.get(current.parent_span_id)
            if parent is None:
                break
            if parent.agent_name:
                return parent.agent_name
            current = parent
        return span.agent_name or ""

    def _apply_trace_filters(self, statement: Any, search: TraceSearch) -> Any:
        filters: dict[str, tuple[str, bool, bool, bool]] = {
            "claim_number": (search.claim_number, True, True, True),
            "audit_run_id": (search.audit_run_id, True, True, False),
            "source": (search.source, True, True, False),
            "source_run_id": (search.source_run_id, True, True, False),
            "batch_id": (search.batch_id, True, True, False),
            "eval_run_id": (search.eval_run_id, True, True, False),
            "optimization_run_id": (search.optimization_run_id, True, True, False),
            "case_id": (search.case_id, True, True, False),
            "status_code": (search.status_code, False, False, False),
            "error_type": (search.error_type, True, False, False),
        }
        for column_name, (
            value,
            include_child_spans,
            include_artifacts,
            partial,
        ) in filters.items():
            values = _split_filter(value)
            if not values:
                continue
            trace_conditions = [
                _column_filter(getattr(AuditTraceORM, column_name), values, partial=partial)
            ]
            if include_child_spans:
                trace_conditions.append(
                    AuditTraceORM.trace_id.in_(
                        select(AuditSpanORM.trace_id).where(
                            _column_filter(
                                getattr(AuditSpanORM, column_name),
                                values,
                                partial=partial,
                            )
                        )
                    )
                )
            artifact_column = getattr(AuditArtifactORM, column_name, None)
            if include_artifacts and artifact_column is not None:
                trace_conditions.append(
                    AuditTraceORM.trace_id.in_(
                        select(AuditArtifactORM.trace_id).where(
                            _column_filter(artifact_column, values, partial=partial)
                        )
                    )
                )
            statement = statement.where(or_(*trace_conditions))
        if search.agent_name:
            agent_names = _split_filter(search.agent_name)
            trace_ids = select(AuditSpanORM.trace_id).where(
                AuditSpanORM.agent_name.in_(agent_names)
                if len(agent_names) > 1
                else AuditSpanORM.agent_name == search.agent_name
            )
            statement = statement.where(AuditTraceORM.trace_id.in_(trace_ids))
        if search.model_name:
            model_names = _split_filter(search.model_name)
            trace_ids = select(AuditSpanORM.trace_id).where(
                AuditSpanORM.model_name.in_(model_names)
                if len(model_names) > 1
                else AuditSpanORM.model_name == search.model_name
            )
            statement = statement.where(AuditTraceORM.trace_id.in_(trace_ids))
        if search.provider_name:
            provider_names = _split_filter(search.provider_name)
            trace_ids = select(AuditSpanORM.trace_id).where(
                AuditSpanORM.provider_name.in_(provider_names)
                if len(provider_names) > 1
                else AuditSpanORM.provider_name == search.provider_name
            )
            statement = statement.where(AuditTraceORM.trace_id.in_(trace_ids))
        if search.tool_name:
            tool_names = _split_filter(search.tool_name)
            trace_ids = select(AuditSpanORM.trace_id).where(
                AuditSpanORM.tool_name.in_(tool_names)
                if len(tool_names) > 1
                else AuditSpanORM.tool_name == search.tool_name
            )
            statement = statement.where(AuditTraceORM.trace_id.in_(trace_ids))
        if search.span_type:
            span_types = _split_filter(search.span_type)
            trace_ids = select(AuditSpanORM.trace_id).where(
                AuditSpanORM.span_type.in_(span_types)
                if len(span_types) > 1
                else AuditSpanORM.span_type == search.span_type
            )
            statement = statement.where(AuditTraceORM.trace_id.in_(trace_ids))
        if search.started_at_from:
            statement = statement.where(AuditTraceORM.started_at >= search.started_at_from)
        if search.started_at_to:
            statement = statement.where(AuditTraceORM.started_at <= search.started_at_to)
        if search.text_query:
            pattern = f"%{search.text_query}%"
            artifact_trace_ids = select(AuditArtifactORM.trace_id).where(
                or_(
                    AuditArtifactORM.content_preview.ilike(pattern),
                    AuditArtifactORM.content_text.ilike(pattern),
                )
            )
            statement = statement.where(AuditTraceORM.trace_id.in_(artifact_trace_ids))
        return statement

    def _apply_span_filters(self, statement: Any, search: TraceSearch) -> Any:
        filters = {
            "claim_number": search.claim_number,
            "audit_run_id": search.audit_run_id,
            "source": search.source,
            "source_run_id": search.source_run_id,
            "batch_id": search.batch_id,
            "eval_run_id": search.eval_run_id,
            "optimization_run_id": search.optimization_run_id,
            "case_id": search.case_id,
            "span_type": search.span_type,
            "status_code": search.status_code,
            "error_type": search.error_type,
            "agent_name": search.agent_name,
            "model_name": search.model_name,
            "provider_name": search.provider_name,
            "tool_name": search.tool_name,
        }
        for column_name, value in filters.items():
            values = _split_filter(value)
            if values:
                statement = statement.where(
                    _column_filter(
                        getattr(AuditSpanORM, column_name),
                        values,
                        partial=column_name == "claim_number",
                    )
                )
        if search.started_at_from:
            statement = statement.where(AuditSpanORM.started_at >= search.started_at_from)
        if search.started_at_to:
            statement = statement.where(AuditSpanORM.started_at <= search.started_at_to)
        return statement
