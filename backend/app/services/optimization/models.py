from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.models.audit import AuditFormResult


@dataclass
class OptimizationDataInstance:
    case_id: str
    claim_number: str
    effective_date: str | None
    instructions: str
    user_prompt: str
    form_path: str
    tools: list[str]
    knowledge_docs: list[str]
    references: list[tuple[str, AuditFormResult]]
    split: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class OptimizationRolloutOutput:
    result: AuditFormResult | None
    success: bool
    error_message: str | None = None
    comparison: dict[str, Any] | None = None
    feedback: str | None = None
    usage: dict[str, int] = field(default_factory=dict)


@dataclass
class OptimizationTrajectory:
    case_id: str
    messages: list[dict[str, Any]]
    reflection_trace: dict[str, Any]
    final_output: dict[str, Any] | None
    error: str | None
    feedback: str | None
    score: float
    usage: dict[str, int]
