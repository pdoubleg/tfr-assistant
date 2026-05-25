from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel
from pydantic.fields import FieldInfo
from pydantic_ai.usage import RunUsage


def now_utc() -> datetime:
    return datetime.now(UTC)


def json_safe(value: Any, *, max_text_chars: int = 4000, depth: int = 0) -> Any:
    if depth > 5:
        return repr(value)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return value if len(value) <= max_text_chars else value[:max_text_chars] + "..."
    if isinstance(value, BaseModel):
        return json_safe(
            value.model_dump(mode="json"),
            max_text_chars=max_text_chars,
            depth=depth + 1,
        )
    if isinstance(value, dict):
        return {
            str(key): json_safe(item, max_text_chars=max_text_chars, depth=depth + 1)
            for key, item in value.items()
        }
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [json_safe(item, max_text_chars=max_text_chars, depth=depth + 1) for item in value]
    return repr(value)


def _is_skip_json_schema_field(field: FieldInfo) -> bool:
    return any(metadata.__class__.__name__ == "SkipJsonSchema" for metadata in field.metadata)


def llm_visible_dump(value: Any) -> Any:
    """Dump Pydantic models as the optimizing LLM sees them in tool schemas."""

    if isinstance(value, BaseModel):
        output: dict[str, Any] = {}
        for name, field in type(value).model_fields.items():
            if _is_skip_json_schema_field(field):
                continue
            output[name] = llm_visible_dump(getattr(value, name))
        return output
    if isinstance(value, dict):
        return {str(key): llm_visible_dump(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [llm_visible_dump(item) for item in value]
    return json_safe(value)


def json_hash(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode(
        "utf-8"
    )
    return hashlib.sha256(encoded).hexdigest()


def usage_to_dict(usage: RunUsage | None, *, tool_calls: int = 0) -> dict[str, int]:
    if usage is None:
        return {"tool_calls": int(tool_calls)} if tool_calls else {}
    data = {
        key: int(value) for key, value in usage.__dict__.items() if isinstance(value, int) and value
    }
    if tool_calls:
        data["tool_calls"] = max(data.get("tool_calls", 0), int(tool_calls))
    data["total_tokens"] = int(usage.total_tokens)
    return data


def merge_usage(target: dict[str, int], usage: RunUsage | None, *, tool_calls: int = 0) -> None:
    for key, value in usage_to_dict(usage, tool_calls=tool_calls).items():
        target[key] = target.get(key, 0) + value
