from types import SimpleNamespace

import pytest
from pydantic_ai.usage import RunUsage

from app.agents import review_agent
from app.agents.review_agent import _populate_runtime_metadata
from app.core.llm import LLMModelAPI, LLMModelConfig, LLMRunCostTracker
from app.models.audit import AuditFormResult


def _audit_result() -> AuditFormResult:
    return AuditFormResult(
        form_id="tfr_default",
        form_version="v0.2",
        title="Runtime metadata test",
        description="Runtime metadata test form",
        questions=[],
        overall_outcome="Meets",
        outcome_justification="Test result.",
    )


def test_populate_runtime_metadata_sets_cost_and_latency(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(review_agent.time, "perf_counter", lambda: 12.34567)
    output = _audit_result()
    deps = SimpleNamespace(cost_tracker=LLMRunCostTracker())

    _populate_runtime_metadata(
        output,
        deps=deps,
        usage=RunUsage(input_tokens=10, output_tokens=5),
        model_config=LLMModelConfig(model_name="test", api=LLMModelAPI.TEST),
        source="unit_test",
        started_at=10.0,
    )

    assert output.cost == 0.0
    assert output.latency == 2.3457
    assert deps.cost_tracker.steps[0].source == "unit_test"
