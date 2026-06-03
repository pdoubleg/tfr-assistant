import pytest
from openai import AsyncOpenAI
from pydantic_ai.models.openai import OpenAIChatModel, OpenAIResponsesModel
from pydantic_ai.models.test import TestModel
from pydantic_ai.usage import RunUsage

from app.agents.chat_agent import build_chat_model
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


def test_build_chat_model_uses_test_model_for_local_mode() -> None:
    model = build_chat_model(Settings(chat_model_api=LLMModelAPI.TEST))

    assert isinstance(model, TestModel)


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
    assert model.settings == {"timeout": 30, "openai_reasoning_effort": "high"}


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
