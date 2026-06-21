from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

from app.core.config import Settings

CONTENT_ATTRIBUTE_KEYS = {
    "gen_ai.input.messages": "llm_input_messages",
    "gen_ai.output.messages": "llm_output_messages",
    "gen_ai.system_instructions": "system_instructions",
    "pydantic_ai.all_messages": "pydantic_ai_all_messages",
    "gen_ai.tool.call.arguments": "tool_arguments",
    "gen_ai.tool.call.result": "tool_result",
    "tool_arguments": "tool_arguments",
    "tool_response": "tool_result",
}


@dataclass(slots=True)
class ArtifactCandidate:
    artifact_key: str
    artifact_type: str
    name: str
    content_text: str
    content_format: str = "text"
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def content_sha256(self) -> str:
        return hashlib.sha256(self.content_text.encode("utf-8", errors="ignore")).hexdigest()

    @property
    def content_size(self) -> int:
        return len(self.content_text.encode("utf-8", errors="ignore"))


def content_to_text(value: Any) -> tuple[str, str]:
    if isinstance(value, str):
        return value, "text"
    try:
        return json.dumps(value, ensure_ascii=False, indent=2, default=str), "json"
    except TypeError:
        return str(value), "text"


def preview_text(text: str, limit: int) -> str:
    if limit <= 0 or len(text) <= limit:
        return text
    return text[:limit]


def extract_artifacts_from_attributes(
    attributes: dict[str, Any],
    settings: Settings,
) -> tuple[dict[str, Any], list[ArtifactCandidate]]:
    sanitized: dict[str, Any] = {}
    artifacts: list[ArtifactCandidate] = []
    max_inline = max(settings.observability_max_inline_attribute_chars, 0)

    for key, value in attributes.items():
        artifact_type = CONTENT_ATTRIBUTE_KEYS.get(key)
        if artifact_type is not None:
            content_text, content_format = content_to_text(value)
            candidate = ArtifactCandidate(
                artifact_key=key,
                artifact_type=artifact_type,
                name=key,
                content_text=content_text,
                content_format=content_format,
                metadata={"otel_attribute": key},
            )
            artifacts.append(candidate)
            sanitized[key] = {
                "artifact_ref": {
                    "artifact_key": key,
                    "artifact_type": artifact_type,
                    "sha256": candidate.content_sha256,
                    "size": candidate.content_size,
                }
            }
            continue

        if isinstance(value, str) and max_inline and len(value) > max_inline:
            candidate = ArtifactCandidate(
                artifact_key=key,
                artifact_type="span_attribute",
                name=key,
                content_text=value,
                metadata={"otel_attribute": key, "externalized_reason": "max_inline_chars"},
            )
            artifacts.append(candidate)
            sanitized[key] = {
                "artifact_ref": {
                    "artifact_key": key,
                    "artifact_type": "span_attribute",
                    "sha256": candidate.content_sha256,
                    "size": candidate.content_size,
                }
            }
            continue

        sanitized[key] = value

    return sanitized, artifacts


def build_manual_artifact(
    *,
    artifact_key: str,
    artifact_type: str,
    content: Any,
    name: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> ArtifactCandidate:
    content_text, content_format = content_to_text(content)
    return ArtifactCandidate(
        artifact_key=artifact_key,
        artifact_type=artifact_type,
        name=name or artifact_key,
        content_text=content_text,
        content_format=content_format,
        metadata=metadata or {},
    )
