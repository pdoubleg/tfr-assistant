from __future__ import annotations

import hashlib
from typing import Any

from pydantic_ai.messages import (
    BuiltinToolCallPart,
    BuiltinToolReturnPart,
    ModelMessage,
    ModelRequest,
    ModelResponse,
    RetryPromptPart,
    SystemPromptPart,
    ThinkingPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)

from app.schemas.optimizations import OptimizationTraceConfig


def serialize_messages(
    messages: list[ModelMessage],
    trace_config: OptimizationTraceConfig,
) -> list[dict[str, Any]]:
    return [serialize_message(message, trace_config) for message in messages]


def count_tool_calls(messages: list[ModelMessage]) -> int:
    total = 0
    for message in messages:
        parts = getattr(message, "parts", [])
        total += sum(1 for part in parts if isinstance(part, (ToolCallPart, BuiltinToolCallPart)))
    return total


def truncate_tool_return(content: str, limit: int) -> dict[str, Any]:
    digest = hashlib.sha256(content.encode("utf-8", errors="ignore")).hexdigest()
    truncated = len(content) > limit
    return {
        "content": content[:limit] if truncated else content,
        "original_char_count": len(content),
        "truncated": truncated,
        "sha256": digest,
    }


def serialize_message(
    message: ModelMessage,
    trace_config: OptimizationTraceConfig,
) -> dict[str, Any]:
    if isinstance(message, ModelRequest):
        return {
            "kind": "request",
            "instructions": message.instructions,
            "parts": [serialize_part(part, trace_config) for part in message.parts],
        }
    if isinstance(message, ModelResponse):
        return {
            "kind": "response",
            "model_name": message.model_name,
            "finish_reason": message.finish_reason,
            "timestamp": message.timestamp.isoformat() if message.timestamp else None,
            "parts": [serialize_part(part, trace_config) for part in message.parts],
        }
    return {"kind": type(message).__name__, "repr": repr(message)}


def serialize_part(part: Any, trace_config: OptimizationTraceConfig) -> dict[str, Any]:
    if isinstance(part, SystemPromptPart):
        return {"type": "system_prompt", "content": part.content}
    if isinstance(part, UserPromptPart):
        return {"type": "user_prompt", "content": str(part.content)}
    if isinstance(part, (ToolCallPart, BuiltinToolCallPart)):
        return {
            "type": "tool_call",
            "tool_name": part.tool_name,
            "arguments": part.args_as_json_str(),
            "tool_call_id": part.tool_call_id,
        }
    if isinstance(part, (ToolReturnPart, BuiltinToolReturnPart)):
        truncated = truncate_tool_return(
            part.model_response_str(),
            trace_config.max_tool_return_chars,
        )
        return {
            "type": "tool_return",
            "tool_name": part.tool_name,
            "tool_call_id": part.tool_call_id,
            **truncated,
        }
    if isinstance(part, RetryPromptPart):
        return {
            "type": "retry_prompt",
            "content": str(part.content),
            "tool_name": part.tool_name,
            "tool_call_id": part.tool_call_id,
        }
    if isinstance(part, ThinkingPart):
        if not trace_config.include_thinking:
            return {"type": "thinking", "omitted": True}
        return {
            "type": "thinking",
            "content": part.content,
            "id": part.id,
            "signature": part.signature,
            "provider_name": part.provider_name,
            "provider_details": part.provider_details,
        }
    content = getattr(part, "content", None)
    return {"type": getattr(part, "part_kind", type(part).__name__), "content": str(content)}
