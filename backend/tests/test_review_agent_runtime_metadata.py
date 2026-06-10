import asyncio
from types import SimpleNamespace

import pytest
from pydantic_ai import ToolDefinition
from pydantic_ai.usage import RunUsage

from app.agents import review_agent
from app.agents.review_agent import (
    _populate_runtime_metadata,
    _prepare_review_agent_tools,
    build_file_review_agent,
)
from app.core.llm import LLMModelAPI, LLMModelConfig, LLMRunCostTracker
from app.models.audit import AuditFormResult
from app.schemas.forms import ALL_REVIEW_AGENT_TOOLS, ReviewAgentToolName


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


def test_review_agent_registers_every_canonical_form_tool() -> None:
    agent = build_file_review_agent(
        model_config=LLMModelConfig(model_name="test", api=LLMModelAPI.TEST),
    )

    assert set(agent._function_toolset.tools) == {tool.value for tool in ALL_REVIEW_AGENT_TOOLS}


def test_prepare_review_agent_tools_filters_to_enabled_pairs() -> None:
    ctx = SimpleNamespace(
        deps=SimpleNamespace(
            tools=[
                ReviewAgentToolName.GET_CLAIM_DOCUMENTS_METADATA.value,
                ReviewAgentToolName.GET_CLAIM_DOCUMENT_CONTENT.value,
                ReviewAgentToolName.GET_POLICY_DOCUMENTS_METADATA.value,
                ReviewAgentToolName.GET_POLICY_DOCUMENT_CONTENT.value,
            ]
        )
    )
    tool_defs = [ToolDefinition(name=tool.value) for tool in ALL_REVIEW_AGENT_TOOLS]

    prepared = asyncio.run(_prepare_review_agent_tools(ctx, tool_defs))

    assert [tool_def.name for tool_def in prepared or []] == [
        ReviewAgentToolName.GET_CLAIM_DOCUMENTS_METADATA.value,
        ReviewAgentToolName.GET_CLAIM_DOCUMENT_CONTENT.value,
        ReviewAgentToolName.GET_POLICY_DOCUMENTS_METADATA.value,
        ReviewAgentToolName.GET_POLICY_DOCUMENT_CONTENT.value,
    ]
