from __future__ import annotations

import pytest
from gepa.core.adapter import EvaluationBatch
from pydantic import ValidationError
from pydantic_ai import Agent
from pydantic_ai.messages import ModelRequest, ModelResponse, ThinkingPart, ToolReturnPart
from pydantic_ai.models.test import TestModel

from app.models.audit import AuditFormResult, FormQuestion, FormSubQuestion
from app.schemas.optimizations import (
    OptimizationGepaParams,
    OptimizationRunCreate,
    OptimizationTraceConfig,
)
from app.services.optimization.runner import auto_budget, estimate_metric_budget
from app.services.optimization_service import (
    AuditPromptProgram,
    OptimizationDataInstance,
    OptimizationRolloutOutput,
    OptimizationTrajectory,
    ProposalOutput,
    ReflectionInput,
    TFRGepaAdapter,
    UpdatedComponent,
    _serialize_messages,
    build_reflection_input,
)


def _sub_question(subquestion_id: str, *, answer: bool) -> FormSubQuestion:
    return FormSubQuestion(
        id=subquestion_id,
        text=f"{subquestion_id} text",
        answer=answer,
        reasoning=f"{subquestion_id} reasoning" if answer else "",
        citations=f"{subquestion_id} citation" if answer else "",
    )


def _result(
    *,
    q1_answer: str = "Yes",
    q2_answer: str = "Yes",
    q3_answer: str = "Yes",
    q3_drivers: tuple[bool, bool] = (False, False),
    outcome: str = "Meets",
) -> AuditFormResult:
    return AuditFormResult(
        form_id="demo",
        form_version="v0.1",
        title="Demo",
        description="Demo form",
        questions=[
            FormQuestion(
                id="Q1",
                text="Allowed?",
                answer=q1_answer,  # type: ignore[arg-type]
                comments="Q1 comment",
                citations="Q1 citation",
            ),
            FormQuestion(
                id="Q2",
                text="Amount ok?",
                answer=q2_answer,  # type: ignore[arg-type]
                comments="Q2 comment",
                citations="Q2 citation",
            ),
            FormQuestion(
                id="Q3",
                text="Drivers clear?",
                answer=q3_answer,  # type: ignore[arg-type]
                sub_questions=[
                    _sub_question("Q3.1", answer=q3_drivers[0]),
                    _sub_question("Q3.2", answer=q3_drivers[1]),
                ],
            ),
        ],
        overall_outcome=outcome,  # type: ignore[arg-type]
        outcome_justification=f"{outcome} rationale",
    )


def test_prompt_program_overrides_string_instructions_and_preserves_callables() -> None:
    agent = Agent(TestModel(custom_output_text="ok"), output_type=str, instructions="original")

    @agent.instructions
    def dynamic_instructions() -> str:
        return "CALLABLE_CONTEXT"

    with AuditPromptProgram({"instructions": "candidate instructions"}).apply_to(agent):
        result = agent.run_sync("hello")

    request = next(
        message for message in result.new_messages() if isinstance(message, ModelRequest)
    )
    assert request.instructions
    assert "candidate instructions" in request.instructions
    assert "CALLABLE_CONTEXT" in request.instructions
    assert "original" not in request.instructions


def test_metric_modes_keep_deterministic_score_and_append_judge_feedback(tmp_path) -> None:
    generated = _result(q2_answer="Yes", q3_answer="Yes", outcome="Meets")
    reference = _result(
        q2_answer="No",
        q3_answer="No",
        q3_drivers=(True, False),
        outcome="Does Not Meet",
    )
    request = OptimizationRunCreate(
        name="metric test",
        form_id="demo",
        form_version="v0.1",
        metric_mode="comparison_with_judge",
        score_key="question_agreement",
        case_splits=[
            {"case_id": "case-1", "split": "train"},
            {"case_id": "case-2", "split": "val"},
        ],
    )
    adapter = TFRGepaAdapter(
        agent=Agent(TestModel(custom_output_text="ok"), output_type=str),
        config=request,
        trace_config=OptimizationTraceConfig(),
        artifact_writer=_Writer(tmp_path),
        proposer_model_config=_test_model_config(),
        judge_model_config=_test_model_config(),
    )
    adapter._judge_feedback = lambda *_args: "judge says fix the amount threshold"  # type: ignore[method-assign]

    instance = OptimizationDataInstance(
        case_id="case-1",
        claim_number="CLAIM",
        effective_date=None,
        instructions="",
        user_prompt="",
        form_path="",
        tools=[],
        knowledge_docs=[],
        references=[("R2", reference)],
        split="train",
    )

    score, feedback, comparison = adapter._score(instance, generated, None)

    assert score == comparison["references"][0]["question_agreement"]
    assert "judge says fix the amount threshold" in feedback
    assert "Q2 mismatch" in feedback


def test_trace_serializer_truncates_tool_returns_and_keeps_thinking() -> None:
    messages = [
        ModelResponse(
            parts=[
                ThinkingPart(content="full thinking trace", provider_name="test"),
                ToolReturnPart(tool_name="lookup", content="x" * 140, tool_call_id="call-1"),
            ],
            model_name="test",
        )
    ]
    trace = _serialize_messages(
        messages,
        OptimizationTraceConfig(max_tool_return_chars=100, include_thinking=True),
    )

    parts = trace[0]["parts"]
    assert parts[0]["type"] == "thinking"
    assert parts[0]["content"] == "full thinking trace"
    assert parts[1]["type"] == "tool_return"
    assert parts[1]["content"] == "x" * 100
    assert parts[1]["original_char_count"] == 140
    assert parts[1]["truncated"] is True


def test_reflection_input_ports_gepadantic_component_contract() -> None:
    assert "Identify patterns in successes and failures" in (ReflectionInput.__doc__ or "")
    assert "components_to_update" in (ReflectionInput.__doc__ or "")

    reflection_input = build_reflection_input(
        {"instructions": ["Seed rule", "Second rule"]},
        {"traces": [{"instructions": ["Original", "Instructions"], "feedback": "missed Q2"}]},
        ["instructions"],
    )
    assert reflection_input.instructions == "Original\n\nInstructions"
    assert reflection_input.prompt_components == {"instructions": "Seed rule\n\nSecond rule"}
    assert "instructions" not in reflection_input.reflection_dataset["traces"][0]

    output = ProposalOutput(
        updated_components=[
            UpdatedComponent(component_name="instructions", optimized_value="Better instructions")
        ]
    )
    assert output.updated_components[0].component_name == "instructions"


def test_reflective_dataset_uses_shared_trace_bucket(tmp_path) -> None:
    request = OptimizationRunCreate(
        name="reflection dataset test",
        form_id="demo",
        form_version="v0.1",
        case_splits=[
            {"case_id": "case-1", "split": "train"},
            {"case_id": "case-2", "split": "val"},
        ],
    )
    adapter = TFRGepaAdapter(
        agent=Agent(TestModel(custom_output_text="ok"), output_type=str),
        config=request,
        trace_config=OptimizationTraceConfig(),
        artifact_writer=_Writer(tmp_path),
        proposer_model_config=_test_model_config(),
        judge_model_config=None,
    )
    batch = EvaluationBatch(
        outputs=[OptimizationRolloutOutput(result=None, success=False, feedback="Q2 mismatch")],
        scores=[0.25],
        trajectories=[
            OptimizationTrajectory(
                case_id="case-1",
                messages=[],
                reflection_trace={"prompt": "receipt"},
                final_output=None,
                error=None,
                feedback="Q2 mismatch",
                score=0.25,
                usage={},
            )
        ],
    )

    dataset = adapter.make_reflective_dataset(
        {"instructions": "current"},
        batch,
        ["instructions"],
    )

    assert list(dataset) == ["traces"]
    assert dataset["traces"][0]["instructions"] == "current"
    assert dataset["traces"][0]["feedback"] == "Q2 mismatch"


def test_gepa_budget_modes_are_mutually_exclusive() -> None:
    assert OptimizationGepaParams(max_metric_calls=10).max_metric_calls == 10
    assert OptimizationGepaParams(max_metric_calls=None, max_full_evals=2).max_full_evals == 2
    assert OptimizationGepaParams(max_metric_calls=None, auto="light").auto == "light"

    for invalid in (
        {"max_metric_calls": None},
        {"max_metric_calls": 10, "max_full_evals": 2},
        {"max_metric_calls": 10, "auto": "light"},
        {"max_metric_calls": None, "max_full_evals": 2, "auto": "light"},
    ):
        with pytest.raises(ValidationError):
            OptimizationGepaParams(**invalid)  # type: ignore[arg-type]


def test_gepa_budget_estimator_matches_config_modes() -> None:
    assert (
        estimate_metric_budget(
            OptimizationGepaParams(max_metric_calls=9),
            train_count=12,
            val_count=4,
        )
        == 9
    )
    assert (
        estimate_metric_budget(
            OptimizationGepaParams(max_metric_calls=None, max_full_evals=3),
            train_count=12,
            val_count=4,
        )
        == 48
    )
    assert estimate_metric_budget(
        OptimizationGepaParams(max_metric_calls=None, auto="light"),
        train_count=12,
        val_count=4,
    ) == auto_budget(num_candidates=6, valset_size=4)


class _Writer:
    def __init__(self, root) -> None:
        self.root = root

    def append_trace(self, _trace) -> None:
        return None


def _test_model_config():
    from app.core.llm import LLMModelAPI, LLMModelConfig

    return LLMModelConfig(model_name="test", api=LLMModelAPI.TEST)
