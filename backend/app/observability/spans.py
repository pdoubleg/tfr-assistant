from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any


def ns_to_datetime(value: int | None) -> datetime | None:
    if value is None:
        return None
    return datetime.fromtimestamp(value / 1_000_000_000, tz=UTC)


def span_id_hex(value: int | None) -> str | None:
    if value is None:
        return None
    return f"{value:016x}"


def trace_id_hex(value: int | None) -> str | None:
    if value is None:
        return None
    return f"{value:032x}"


def json_safe(value: Any) -> Any:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, tuple | set):
        return [json_safe(item) for item in value]
    if isinstance(value, list):
        return [json_safe(item) for item in value]
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    try:
        json.dumps(value)
        return value
    except TypeError:
        return str(value)


def normalize_readable_span(span: Any) -> dict[str, Any]:
    context = span.get_span_context()
    parent = getattr(span, "parent", None)
    attributes = dict(getattr(span, "attributes", {}) or {})
    resource = getattr(getattr(span, "resource", None), "attributes", {}) or {}
    status = getattr(span, "status", None)
    status_code = getattr(getattr(status, "status_code", None), "name", "UNSET")
    status_description = getattr(status, "description", None)
    events = []
    for index, event in enumerate(getattr(span, "events", ()) or ()):
        event_attributes = dict(getattr(event, "attributes", {}) or {})
        events.append(
            {
                "event_index": index,
                "name": getattr(event, "name", ""),
                "timestamp": ns_to_datetime(getattr(event, "timestamp", None)),
                "attributes": json_safe(event_attributes),
            }
        )

    started_at = ns_to_datetime(getattr(span, "start_time", None))
    ended_at = ns_to_datetime(getattr(span, "end_time", None))
    duration_ms = None
    if started_at and ended_at:
        duration_ms = int(max(0, (ended_at - started_at).total_seconds() * 1000))

    trace_id = trace_id_hex(context.trace_id)
    span_id = span_id_hex(context.span_id)
    parent_span_id = span_id_hex(parent.span_id) if parent is not None else None

    return {
        "trace_id": trace_id,
        "span_id": span_id,
        "parent_span_id": parent_span_id,
        "name": getattr(span, "name", ""),
        "kind": getattr(getattr(span, "kind", None), "name", ""),
        "status_code": status_code,
        "status_description": status_description,
        "started_at": started_at,
        "ended_at": ended_at,
        "duration_ms": duration_ms,
        "attributes": json_safe(attributes),
        "resource": json_safe(dict(resource)),
        "events": events,
    }


def first_present(attributes: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = attributes.get(key)
        if value is not None and value != "":
            return value
    return None


def int_attr(attributes: dict[str, Any], *keys: str) -> int:
    value = first_present(attributes, *keys)
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str) and value.strip().isdigit():
        return int(value)
    return 0


def float_attr(attributes: dict[str, Any], *keys: str) -> float | None:
    value = first_present(attributes, *keys)
    if isinstance(value, int | float) and not isinstance(value, bool):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def classify_span(name: str, attributes: dict[str, Any]) -> str:
    if first_present(
        attributes,
        "db.system",
        "db.statement",
        "db.operation",
        "db.operation.name",
        "db.query.text",
        "db.name",
        "db.namespace",
    ):
        return "db"
    operation = str(attributes.get("gen_ai.operation.name") or "").strip()
    if operation == "invoke_agent":
        return "agent"
    if operation == "execute_tool":
        return "tool"
    if operation in {"chat", "generate_content", "text_completion"}:
        return "model"
    if operation:
        return operation
    lowered = name.lower()
    if lowered.startswith("invoke_agent") or "agent run" in lowered:
        return "agent"
    if lowered.startswith("execute_tool") or "running tool" in lowered:
        return "tool"
    if "chat" in lowered or "model" in lowered or "completion" in lowered:
        return "model"
    if lowered.startswith(("select ", "insert ", "update ", "delete ", "commit", "rollback")):
        return "db"
    return ""


def extract_span_columns(span: dict[str, Any]) -> dict[str, Any]:
    attributes = span["attributes"]
    name = span.get("name") or ""
    error_type = first_present(attributes, "error.type", "exception.type")
    error_message = None
    for event in span.get("events", []):
        event_attrs = event.get("attributes") or {}
        error_type = error_type or first_present(event_attrs, "exception.type")
        error_message = error_message or first_present(event_attrs, "exception.message")

    input_tokens = int_attr(
        attributes,
        "gen_ai.usage.input_tokens",
        "gen_ai.usage.prompt_tokens",
        "gen_ai.aggregated_usage.input_tokens",
        "gen_ai.aggregated_usage.prompt_tokens",
    )
    output_tokens = int_attr(
        attributes,
        "gen_ai.usage.output_tokens",
        "gen_ai.usage.completion_tokens",
        "gen_ai.aggregated_usage.output_tokens",
        "gen_ai.aggregated_usage.completion_tokens",
    )
    total_tokens = int_attr(
        attributes,
        "gen_ai.usage.total_tokens",
        "gen_ai.aggregated_usage.total_tokens",
    )
    if not total_tokens:
        total_tokens = input_tokens + output_tokens

    return {
        "span_type": classify_span(name, attributes),
        "agent_name": str(first_present(attributes, "gen_ai.agent.name") or ""),
        "model_name": str(
            first_present(attributes, "gen_ai.response.model", "gen_ai.request.model") or ""
        ),
        "provider_name": str(
            first_present(attributes, "gen_ai.provider.name", "gen_ai.system") or ""
        ),
        "tool_name": str(
            first_present(attributes, "gen_ai.tool.name", "gen_ai.tool.call.name") or ""
        ),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "estimated_cost_usd": float_attr(
            attributes,
            "gen_ai.usage.cost_usd",
            "gen_ai.response.cost_usd",
            "llm.cost_usd",
        ),
        "error_type": str(error_type) if error_type else None,
        "error_message": str(error_message) if error_message else None,
    }


def extract_audit_columns(attributes: dict[str, Any]) -> dict[str, Any]:
    return {
        "audit_run_id": first_present(attributes, "audit.run_id"),
        "review_id": first_present(attributes, "audit.review_id", "audit.run_id"),
        "source": first_present(attributes, "audit.source") or "",
        "source_run_id": first_present(attributes, "audit.source_run_id"),
        "batch_id": first_present(attributes, "audit.batch_id"),
        "eval_run_id": first_present(attributes, "audit.eval_run_id"),
        "eval_dataset_id": first_present(attributes, "audit.eval_dataset_id"),
        "optimization_run_id": first_present(attributes, "audit.optimization_run_id"),
        "case_id": first_present(attributes, "audit.case_id", "gen_ai.data_source.id"),
        "claim_number": first_present(attributes, "audit.claim_number") or "",
        "form_id": first_present(attributes, "audit.form_id") or "",
        "form_version": first_present(attributes, "audit.form_version") or "",
        "form_kind": first_present(attributes, "audit.form_kind") or "",
        "tenant_id": first_present(attributes, "audit.tenant_id"),
        "user_id": first_present(attributes, "audit.user_id"),
    }


def should_persist_span(span: dict[str, Any], *, capture_all: bool) -> bool:
    if capture_all:
        return True
    attributes = span.get("attributes") or {}
    observed = attributes.get("audit.observed")
    return observed is True or str(observed).lower() == "true"
