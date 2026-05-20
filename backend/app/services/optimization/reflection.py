# ruff: noqa: E501

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field
from pydantic_ai import Agent

from app.core.llm import LLMModelConfig, build_llm_model
from app.services.optimization.components import normalize_component_text


class ReflectionInput(BaseModel):
    """Analyze agent performance data and propose improved prompt components.

    Your task is to:
    1. Review the reflection dataset showing how the agent performed with current prompts
    2. Read all the assistant responses and the corresponding feedback
    3. Identify patterns in successes and failures
    4. Identify all niche and domain-specific factual information about the task and include it in
       the instruction, as a lot of it may not be available to the assistant in the future
    5. If the assistant utilized a generalizable strategy to solve the task, include that
       strategy in the instruction as well
    6. Propose specific improvements to the components listed in 'components_to_update'
    7. If useful, include few shot examples of the task to help the assistant understand the task better

    Focus on making prompts clearer, more specific, and better aligned with successful outcomes.
    Extract domain knowledge from the examples to enhance the instructions.
    """

    instructions: str | None = Field(
        default=None,
        description="The instructions that were used by the agent.",
    )
    prompt_components: dict[str, str] = Field(
        description="Current prompt components being used by the agent. These map to the instructions above."
    )
    reflection_dataset: dict[str, list[dict[str, Any]]] = Field(
        description="Performance data showing agent inputs, outputs, scores, and feedback for each component. Analyze these to understand what works and what needs improvement."
    )
    components_to_update: list[str] = Field(
        description="Specific components to optimize in this iteration. Only modify these components in your response while keeping others unchanged."
    )


class UpdatedComponent(BaseModel):
    component_name: str
    optimized_value: str


class ProposalOutput(BaseModel):
    """Optimized prompt components based on performance analysis.

    Provide improved versions of the specified components that:
    - Incorporate specific patterns and domain knowledge from successful examples
    - Address failure patterns identified in the reflection dataset
    - Maintain clarity and specificity while improving effectiveness
    """

    updated_components: list[UpdatedComponent] = Field(
        description="A list of updated prompt components. Only include the components that were specified for update."
    )


def build_reflection_input(
    candidate: dict[str, str],
    reflective_dataset: dict[str, list[dict[str, Any]]],
    components_to_update: list[str],
) -> ReflectionInput:
    instructions: str | None = None
    dataset: dict[str, list[dict[str, Any]]] = {}
    for bucket, records in reflective_dataset.items():
        dataset[bucket] = []
        for raw_record in records:
            record = dict(raw_record)
            if "instructions" in record and not instructions:
                instructions = normalize_component_text(record["instructions"])
            record.pop("instructions", None)
            dataset[bucket].append(record)

    normalized_components = {
        key: normalize_component_text(value) for key, value in candidate.items()
    }
    return ReflectionInput(
        instructions=instructions,
        prompt_components=normalized_components,
        reflection_dataset=dataset,
        components_to_update=components_to_update,
    )


def render_reflection_prompt(reflection_input: ReflectionInput) -> str:
    return json.dumps(reflection_input.model_dump(mode="json"), ensure_ascii=True, default=str)


def propose_new_texts(
    candidate: dict[str, str],
    reflective_dataset: dict[str, list[dict[str, Any]]],
    components_to_update: list[str],
    proposer_model_config: LLMModelConfig,
):
    """Analyze performance and propose optimized prompt components."""

    reflection_input = build_reflection_input(
        candidate,
        reflective_dataset,
        components_to_update,
    )
    agent = Agent(
        build_llm_model(proposer_model_config),
        output_type=ProposalOutput,
        instructions=ReflectionInput.__doc__,
        output_retries=3,
    )
    return agent.run_sync(render_reflection_prompt(reflection_input))
