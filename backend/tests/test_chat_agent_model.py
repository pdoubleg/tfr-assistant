from pydantic_ai.models.openai import OpenAIResponsesModel
from pydantic_ai.models.test import TestModel

from app.agents.chat_agent import build_chat_model
from app.core.config import Settings


def test_build_chat_model_uses_test_model_for_local_mode() -> None:
    model = build_chat_model(Settings(chat_model="test"))

    assert isinstance(model, TestModel)


def test_build_chat_model_uses_responses_model_for_responses_spec() -> None:
    model = build_chat_model(
        Settings(
            chat_model="openai-responses:gpt-5.4-mini",
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


def test_build_chat_model_leaves_legacy_string_specs_to_pydantic_ai() -> None:
    model = build_chat_model(Settings(chat_model="openai:gpt-5.4-mini"))

    assert model == "openai:gpt-5.4-mini"
