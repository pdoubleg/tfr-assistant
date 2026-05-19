from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from openai import AsyncOpenAI
from pydantic import BaseModel
from pydantic_ai.models import Model
from pydantic_ai.models.openai import OpenAIChatModel, OpenAIResponsesModel
from pydantic_ai.models.test import TestModel
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.settings import ModelSettings


class LLMModelAPI(StrEnum):
    CHAT = "chat"
    RESPONSES = "responses"
    TEST = "test"


ReasoningEffort = Literal["low", "medium", "high"]
ReasoningSummary = Literal["auto", "concise", "detailed"]


class LLMModelConfig(BaseModel):
    model_name: str
    api: LLMModelAPI = LLMModelAPI.CHAT
    timeout_seconds: float | None = None
    reasoning_effort: ReasoningEffort | None = None
    reasoning_summary: ReasoningSummary | None = None
    send_reasoning_ids: bool | None = None
    test_output_text: str | None = None

    @property
    def label(self) -> str:
        if self.api == LLMModelAPI.TEST or self.model_name.strip() == "test":
            return "TestModel(test)"
        model_class = (
            "OpenAIResponsesModel" if self.api == LLMModelAPI.RESPONSES else "OpenAIChatModel"
        )
        return f"{model_class}({self.model_name.strip()})"


def build_llm_model(
    config: LLMModelConfig,
    *,
    openai_client: AsyncOpenAI | None = None,
) -> Model[Any]:
    model_name = _model_name(config.model_name)
    if config.api == LLMModelAPI.TEST or model_name == "test":
        return TestModel(custom_output_text=config.test_output_text, model_name="test")

    provider = OpenAIProvider(openai_client=openai_client or AsyncOpenAI())
    model_settings = _model_settings(config)
    if config.api == LLMModelAPI.RESPONSES:
        return OpenAIResponsesModel(model_name, provider=provider, settings=model_settings)
    if config.api == LLMModelAPI.CHAT:
        return OpenAIChatModel(model_name, provider=provider, settings=model_settings)
    raise ValueError(f"Unsupported LLM model API: {config.api}")


def _model_name(value: str) -> str:
    model_name = value.strip()
    if not model_name:
        raise ValueError("LLM model_name cannot be empty.")
    if model_name.startswith(("openai:", "openai-chat:", "openai-responses:")):
        raise ValueError(
            "LLM model_name should be the underlying model name only, for example "
            "'gpt-5.4-mini'. Use the dedicated api setting to choose chat or responses."
        )
    return model_name


def _model_settings(config: LLMModelConfig) -> ModelSettings | None:
    model_settings: ModelSettings = {}
    if config.timeout_seconds is not None:
        model_settings["timeout"] = config.timeout_seconds

    if config.api == LLMModelAPI.RESPONSES:
        if config.send_reasoning_ids is not None:
            model_settings["openai_send_reasoning_ids"] = config.send_reasoning_ids
        if config.reasoning_effort:
            model_settings["openai_reasoning_effort"] = config.reasoning_effort
        if config.reasoning_summary:
            model_settings["openai_reasoning_summary"] = config.reasoning_summary

    return model_settings or None
