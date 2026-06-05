from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Literal

from genai_prices import Usage as GenAIUsage
from genai_prices import calc_price, data_snapshot
from openai import AsyncOpenAI
from pydantic import BaseModel
from pydantic_ai.models import Model
from pydantic_ai.models.openai import OpenAIChatModel, OpenAIResponsesModel
from pydantic_ai.models.test import TestModel
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.settings import ModelSettings
from pydantic_ai.usage import RunUsage

logger = logging.getLogger(__name__)


class LLMModelAPI(StrEnum):
    CHAT = "chat"
    RESPONSES = "responses"
    TEST = "test"


ReasoningEffort = Literal["none", "minimal", "low", "medium", "high", "xhigh"]
ReasoningSummary = Literal["auto", "concise", "detailed"]

DEFAULT_CHAT_MODEL_NAME = "gpt-5.4-mini"
DEFAULT_AUDIT_MODEL_NAME = "gpt-5.4-nano"


class AvailableLLMModel(BaseModel):
    name: str
    label: str
    base_name: str
    deployment_name: str
    context_window: int | None = None
    api: LLMModelAPI = LLMModelAPI.CHAT
    reasoning_efforts: list[ReasoningEffort] = []
    default_reasoning_effort: ReasoningEffort | None = None
    default_for_chat: bool = False
    default_for_audit: bool = False

    @property
    def supports_reasoning_effort(self) -> bool:
        return bool(self.reasoning_efforts)


AVAILABLE_LLM_MODELS: tuple[AvailableLLMModel, ...] = (
    AvailableLLMModel(
        name="gpt-5.5",
        label="GPT-5.5",
        base_name="gpt-5.5",
        deployment_name="gpt-5.5",
        context_window=1_000_000,
        reasoning_efforts=["minimal", "low", "medium", "high", "xhigh"],
        default_reasoning_effort="medium",
    ),
    AvailableLLMModel(
        name="gpt-5.4",
        label="GPT-5.4",
        base_name="gpt-5.4",
        deployment_name="gpt-5.4",
        context_window=1_050_000,
        reasoning_efforts=["minimal", "low", "medium", "high"],
        default_reasoning_effort="medium",
    ),
    AvailableLLMModel(
        name=DEFAULT_CHAT_MODEL_NAME,
        label="GPT-5.4 Mini",
        base_name=DEFAULT_CHAT_MODEL_NAME,
        deployment_name=DEFAULT_CHAT_MODEL_NAME,
        context_window=400_000,
        reasoning_efforts=["minimal", "low", "medium", "high"],
        default_reasoning_effort="low",
        default_for_chat=True,
    ),
    AvailableLLMModel(
        name=DEFAULT_AUDIT_MODEL_NAME,
        label="GPT-5.4 Nano",
        base_name=DEFAULT_AUDIT_MODEL_NAME,
        deployment_name=DEFAULT_AUDIT_MODEL_NAME,
        context_window=400_000,
        reasoning_efforts=["none", "minimal", "low"],
        default_reasoning_effort="low",
        default_for_audit=True,
    ),
)


class LLMModelConfig(BaseModel):
    model_name: str
    api: LLMModelAPI = LLMModelAPI.CHAT
    base_model_name: str | None = None
    pricing_model_name: str | None = None
    timeout_seconds: float | None = None
    reasoning_effort: ReasoningEffort | None = None
    reasoning_summary: ReasoningSummary | None = None
    send_reasoning_ids: bool | None = None
    test_output_text: str | None = None

    @property
    def deployment_name(self) -> str:
        return _model_name(self.model_name)

    @property
    def pricing_lookup_name(self) -> str:
        return _model_name(
            self.pricing_model_name
            or self.base_model_name
            or base_model_name_for_deployment(self.model_name)
        )

    @property
    def label(self) -> str:
        if self.api == LLMModelAPI.TEST or self.model_name.strip() == "test":
            return "TestModel(test)"
        model_class = (
            "OpenAIResponsesModel" if self.api == LLMModelAPI.RESPONSES else "OpenAIChatModel"
        )
        deployment = self.deployment_name
        pricing_name = self.pricing_lookup_name
        if deployment != pricing_name:
            return f"{model_class}({deployment}; pricing={pricing_name})"
        return f"{model_class}({deployment})"


@dataclass(slots=True)
class LLMRunCostStep:
    source: str
    model_name: str
    pricing_model_name: str
    usage: dict[str, int]
    cost: float


@dataclass(slots=True)
class LLMRunCostTracker:
    steps: list[LLMRunCostStep] = field(default_factory=list)

    def add_usage(
        self,
        usage: RunUsage | None,
        model_config: LLMModelConfig | str,
        *,
        source: str,
    ) -> LLMRunCostStep:
        cost = calculate_token_cost(usage, model_config)
        model_name = (
            model_config.deployment_name
            if isinstance(model_config, LLMModelConfig)
            else _model_name(model_config)
        )
        pricing_model_name = (
            model_config.pricing_lookup_name
            if isinstance(model_config, LLMModelConfig)
            else base_model_name_for_deployment(model_config)
        )
        step = LLMRunCostStep(
            source=source,
            model_name=model_name,
            pricing_model_name=pricing_model_name,
            usage=run_usage_to_dict(usage),
            cost=cost,
        )
        self.steps.append(step)
        return step

    @property
    def total_cost(self) -> float:
        return round(sum(step.cost for step in self.steps), 8)


def build_llm_model(
    config: LLMModelConfig,
    *,
    openai_client: AsyncOpenAI | None = None,
) -> Model[Any]:
    model_name = config.deployment_name
    if config.api == LLMModelAPI.TEST or model_name == "test":
        return TestModel(custom_output_text=config.test_output_text, model_name="test")

    provider = OpenAIProvider(openai_client=openai_client or AsyncOpenAI())
    model_settings = _model_settings(config)
    if config.api == LLMModelAPI.RESPONSES:
        return OpenAIResponsesModel(model_name, provider=provider, settings=model_settings)
    if config.api == LLMModelAPI.CHAT:
        return OpenAIChatModel(model_name, provider=provider, settings=model_settings)
    raise ValueError(f"Unsupported LLM model API: {config.api}")


def available_llm_models(
    *,
    deployment_overrides: dict[str, str] | None = None,
) -> list[AvailableLLMModel]:
    overrides = deployment_overrides or {}
    return [
        option.model_copy(
            update={
                "deployment_name": overrides.get(
                    option.name,
                    overrides.get(option.base_name, option.deployment_name),
                )
            }
        )
        for option in AVAILABLE_LLM_MODELS
    ]


def default_chat_model_name() -> str:
    return next(
        (option.name for option in AVAILABLE_LLM_MODELS if option.default_for_chat),
        DEFAULT_CHAT_MODEL_NAME,
    )


def default_audit_model_name() -> str:
    return next(
        (option.name for option in AVAILABLE_LLM_MODELS if option.default_for_audit),
        DEFAULT_AUDIT_MODEL_NAME,
    )


def resolve_llm_model_option(
    model_name: str,
    *,
    deployment_overrides: dict[str, str] | None = None,
) -> AvailableLLMModel | None:
    value = _model_name(model_name)
    options = available_llm_models(deployment_overrides=deployment_overrides)
    for option in options:
        if value in {option.name, option.base_name, option.deployment_name}:
            return option

    inferred = base_model_name_for_deployment(value)
    for option in options:
        if inferred in {option.name, option.base_name}:
            return option.model_copy(update={"deployment_name": value})
    return None


def llm_model_config_for(
    model_name: str,
    *,
    api: LLMModelAPI = LLMModelAPI.CHAT,
    deployment_overrides: dict[str, str] | None = None,
    base_model_name: str | None = None,
    timeout_seconds: float | None = None,
    reasoning_effort: ReasoningEffort | None = None,
    reasoning_summary: ReasoningSummary | None = None,
    send_reasoning_ids: bool | None = None,
    test_output_text: str | None = None,
) -> LLMModelConfig:
    normalized_model_name = _model_name(model_name)
    if api == LLMModelAPI.TEST or normalized_model_name == "test":
        return LLMModelConfig(
            model_name="test",
            api=LLMModelAPI.TEST,
            base_model_name="test",
            pricing_model_name="test",
            timeout_seconds=timeout_seconds,
            test_output_text=test_output_text,
        )

    option = resolve_llm_model_option(
        base_model_name or normalized_model_name,
        deployment_overrides=deployment_overrides,
    )
    deployment_name = normalized_model_name
    pricing_model_name = base_model_name or base_model_name_for_deployment(normalized_model_name)
    valid_efforts: list[ReasoningEffort] = []
    default_effort: ReasoningEffort | None = None
    if option is not None:
        deployment_name = option.deployment_name
        pricing_model_name = base_model_name or option.base_name
        valid_efforts = option.reasoning_efforts
        default_effort = option.default_reasoning_effort

    selected_effort = reasoning_effort if reasoning_effort is not None else default_effort
    if selected_effort and valid_efforts and selected_effort not in valid_efforts:
        selected_effort = default_effort

    return LLMModelConfig(
        model_name=deployment_name,
        api=api,
        base_model_name=pricing_model_name,
        pricing_model_name=pricing_model_name,
        timeout_seconds=timeout_seconds,
        reasoning_effort=selected_effort,
        reasoning_summary=reasoning_summary,
        send_reasoning_ids=send_reasoning_ids,
        test_output_text=test_output_text,
    )


def base_model_name_for_deployment(model_name: str) -> str:
    normalized = _model_name(model_name)
    options = sorted(AVAILABLE_LLM_MODELS, key=lambda option: len(option.base_name), reverse=True)
    for option in options:
        if normalized == option.base_name or normalized.startswith(f"{option.base_name}-"):
            return option.base_name
        dashed = option.base_name.replace(".", "-")
        if normalized == dashed or normalized.startswith(f"{dashed}-"):
            return option.base_name
    return normalized


def calculate_token_cost(
    usage: RunUsage | None,
    model_config: LLMModelConfig | str,
    *,
    provider_id: str = "openai",
) -> float:
    if usage is None:
        return 0.0
    model_name = (
        model_config.pricing_lookup_name
        if isinstance(model_config, LLMModelConfig)
        else base_model_name_for_deployment(model_config)
    )
    if model_name == "test":
        return 0.0
    genai_usage = GenAIUsage(
        input_tokens=usage.input_tokens or None,
        cache_write_tokens=usage.cache_write_tokens or None,
        cache_read_tokens=usage.cache_read_tokens or None,
        output_tokens=usage.output_tokens or None,
        input_audio_tokens=usage.input_audio_tokens or None,
        cache_audio_read_tokens=usage.cache_audio_read_tokens or None,
        output_audio_tokens=getattr(usage, "output_audio_tokens", 0) or None,
    )
    try:
        price = calc_price(genai_usage, model_name, provider_id=provider_id)
    except Exception as exc:  # pragma: no cover - depends on third-party pricing data freshness.
        logger.warning("Unable to calculate LLM token cost for %s: %s", model_name, exc)
        return 0.0
    return round(float(price.total_price), 8)


def context_window_for_model(
    model_config: LLMModelConfig | str,
    *,
    deployment_overrides: dict[str, str] | None = None,
    provider_id: str = "openai",
) -> int | None:
    if isinstance(model_config, LLMModelConfig):
        model_name = model_config.pricing_lookup_name
    else:
        model_name = base_model_name_for_deployment(model_config)
    if model_name == "test":
        return None

    option = resolve_llm_model_option(
        model_name,
        deployment_overrides=deployment_overrides,
    )
    if option and option.context_window is not None:
        return option.context_window

    try:
        _, model = data_snapshot.get_snapshot().find_provider_model(
            model_name,
            None,
            provider_id,
            None,
        )
    except Exception as exc:  # pragma: no cover - depends on third-party pricing data freshness.
        logger.warning("Unable to look up context window for %s: %s", model_name, exc)
        return None
    return model.context_window


def run_usage_to_dict(usage: RunUsage | None) -> dict[str, int]:
    if usage is None:
        return {}
    data = {
        key: int(value) for key, value in usage.__dict__.items() if isinstance(value, int) and value
    }
    data["total_tokens"] = int(usage.total_tokens)
    return data


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
        if config.reasoning_effort:
            model_settings["openai_reasoning_effort"] = config.reasoning_effort
        if config.send_reasoning_ids is not None:
            model_settings["openai_send_reasoning_ids"] = config.send_reasoning_ids
        if config.reasoning_summary:
            model_settings["openai_reasoning_summary"] = config.reasoning_summary

    return model_settings or None
