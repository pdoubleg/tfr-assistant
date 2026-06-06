from types import SimpleNamespace

import pytest
from openai import AsyncOpenAI
from pydantic_ai.models.openai import OpenAIChatModel, OpenAIResponsesModel
from pydantic_ai.models.test import TestModel
from pydantic_ai.usage import RunUsage

from app.agents.chat_agent import build_chat_model, chat_agent, get_registered_forms_listing
from app.core.config import Settings
from app.core.llm import (
    LLMModelAPI,
    LLMModelConfig,
    base_model_name_for_deployment,
    build_llm_model,
    calculate_token_cost,
    context_window_for_model,
    llm_model_config_for,
)
from app.models.audit import AuditFormResult
from app.presenters.a2ui import generate_audit_review_card
from app.schemas.reviews import ReviewRecord


def test_build_chat_model_uses_test_model_for_local_mode() -> None:
    model = build_chat_model(Settings(chat_model_api=LLMModelAPI.TEST))

    assert isinstance(model, TestModel)


def test_generate_audit_form_review_tool_schema_omits_runtime_prompt() -> None:
    assert "get_registered_forms_listing" in chat_agent._function_toolset.tools
    tool = chat_agent._function_toolset.tools["generate_audit_form_review"]
    schema = tool.function_schema.json_schema

    assert "prompt" not in schema["properties"]
    assert schema["required"] == ["claim_number", "form_id"]


@pytest.mark.anyio
async def test_registered_forms_listing_returns_compact_catalog_metadata() -> None:
    ctx = SimpleNamespace(deps=SimpleNamespace(settings=Settings()))

    listing = await get_registered_forms_listing(ctx)

    assert "Registered audit forms:" in listing
    assert "canonical_form_id=tfr_default" in listing
    assert "form_kind=standard" in listing
    assert "form_id=tfr_default" in listing
    assert "form_version=v0.1" in listing
    assert "title=" in listing
    assert "description=" in listing


def test_audit_review_card_component_opens_generated_result() -> None:
    form = AuditFormResult(
        form_id="tfr_default",
        form_version="v0.1",
        title="Generated review",
        description="Generated form description.",
        questions=[],
        overall_outcome="Meets",
        outcome_justification="Evidence supports the result.",
    )
    review = ReviewRecord(
        id="review-1",
        form_id="tfr_default",
        form_version="v0.1",
        source="chat_tool",
        input_json={"claim_number": "CLAIM-123"},
        original=form,
        user_version=form,
    )

    component = generate_audit_review_card(review)

    assert component is not None
    assert component.type == "a2ui.AuditReviewCard"
    assert component.zone == "chat"
    assert component.props["reviewId"] == "review-1"
    assert component.props["claimNumber"] == "CLAIM-123"
    assert component.props["form"] == form.model_dump(mode="json")


def test_build_chat_model_uses_responses_model_for_responses_api(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    model = build_chat_model(
        Settings(
            chat_model="gpt-5.4-mini",
            chat_model_api=LLMModelAPI.RESPONSES,
            chat_model_reasoning_effort="low",
            chat_model_reasoning_summary="detailed",
            chat_model_timeout_seconds=45,
        )
    )

    assert isinstance(model, OpenAIResponsesModel)
    assert model.model_name == "gpt-5.4-mini"
    assert model.settings == {
        "timeout": 45.0,
        "openai_send_reasoning_ids": False,
        "openai_reasoning_effort": "low",
        "openai_reasoning_summary": "detailed",
    }
    assert model.client is model.provider.client


def test_build_llm_model_uses_chat_model_for_chat_api() -> None:
    model = build_llm_model(
        LLMModelConfig(
            model_name="gpt-5.4-mini",
            api=LLMModelAPI.CHAT,
            timeout_seconds=30,
            reasoning_effort="high",
            reasoning_summary="auto",
        ),
        openai_client=AsyncOpenAI(api_key="test-key"),
    )

    assert isinstance(model, OpenAIChatModel)
    assert model.model_name == "gpt-5.4-mini"
    assert model.settings == {"timeout": 30}


def test_build_llm_model_rejects_legacy_openai_prefixes() -> None:
    with pytest.raises(ValueError, match="underlying model name only"):
        build_llm_model(
            LLMModelConfig(
                model_name="openai-responses:gpt-5.4-mini",
                api=LLMModelAPI.RESPONSES,
            ),
            openai_client=AsyncOpenAI(api_key="test-key"),
        )


def test_llm_model_config_maps_azure_deployment_to_pricing_base() -> None:
    config = llm_model_config_for(
        "gpt-5.5-06-20-2023-us-data-zone",
        api=LLMModelAPI.CHAT,
        reasoning_effort="high",
    )

    assert config.model_name == "gpt-5.5-06-20-2023-us-data-zone"
    assert config.pricing_lookup_name == "gpt-5.5"
    assert config.reasoning_effort == "high"
    assert base_model_name_for_deployment("gpt-5.4-mini-2026-03-17-us") == "gpt-5.4-mini"
    assert context_window_for_model(config) == 1_000_000


def test_llm_model_config_uses_deployment_overrides() -> None:
    config = llm_model_config_for(
        "gpt-5.4-mini",
        api=LLMModelAPI.CHAT,
        deployment_overrides={"gpt-5.4-mini": "azure-gpt-54-mini-prod"},
    )

    assert config.model_name == "azure-gpt-54-mini-prod"
    assert config.pricing_lookup_name == "gpt-5.4-mini"


def test_calculate_token_cost_uses_pricing_lookup_name() -> None:
    config = LLMModelConfig(
        model_name="azure-gpt-54-mini-prod",
        base_model_name="gpt-5.4-mini",
        pricing_model_name="gpt-5.4-mini",
    )

    cost = calculate_token_cost(
        RunUsage(input_tokens=1_000, cache_read_tokens=500, output_tokens=250),
        config,
    )

    assert cost > 0
