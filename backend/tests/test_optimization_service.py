from __future__ import annotations

import pytest
from gepa.core.adapter import EvaluationBatch
from gepa.core.data_loader import ListDataLoader
from pydantic import ValidationError
from pydantic_ai import Agent
from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    ThinkingPart,
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_ai.models.test import TestModel
from pydantic_ai.usage import RunUsage

from app.models.audit import AuditFormResult, FormQuestion, FormSubQuestion
from app.schemas.optimizations import (
    OptimizationGepaParams,
    OptimizationRunCreate,
    OptimizationTraceConfig,
)
from app.services.optimization import (
    AuditBalancedBatchSampler,
    AuditPromptProgram,
    OptimizationDataInstance,
    OptimizationRolloutOutput,
    OptimizationRunService,
    OptimizationTrajectory,
    ProposalOutput,
    ReflectionInput,
    TFRGepaAdapter,
    UpdatedComponent,
    build_reflection_input,
)
from app.services.optimization import (
    serialize_messages as _serialize_messages,
)
from app.services.optimization.runner import auto_budget, estimate_metric_budget
from app.services.optimization.utils import llm_visible_dump, usage_to_dict


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


def _instance(case_id: str, result: AuditFormResult) -> OptimizationDataInstance:
    return OptimizationDataInstance(
        case_id=case_id,
        claim_number=case_id,
        effective_date=None,
        instructions="",
        user_prompt="",
        form_path="",
        tools=[],
        knowledge_docs=[],
        references=[("R2", result)],
        split="train",
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


def test_metric_modes_blend_judge_score_and_pass_prior_feedback(tmp_path) -> None:
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
        use_feedback_when_available=True,
        judge_score_weight=0.25,
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
    captured: dict[str, str] = {}

    def fake_judge(*_args, prior_feedback: str = "") -> tuple[str, float]:
        captured["prior_feedback"] = prior_feedback
        return "judge says fix the amount threshold", 0.2

    adapter._judge_feedback = fake_judge  # type: ignore[method-assign]

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
        metadata={"feedback": {"comments": ["Use better citations for Q2."]}},
    )

    score, feedback, comparison = adapter._score(instance, generated, None)

    deterministic_score = comparison["references"][0]["question_agreement"]
    assert comparison["deterministic_score"] == deterministic_score
    assert comparison["judge_score"] == 0.2
    assert score == pytest.approx((deterministic_score * 0.75) + (0.2 * 0.25))
    assert comparison["score"] == score
    assert "judge says fix the amount threshold" in feedback
    assert "Use better citations for Q2." in feedback
    assert captured["prior_feedback"] == "- Use better citations for Q2."
    assert "Q2 mismatch" in feedback


def test_trace_serializer_truncates_tool_returns_and_keeps_thinking() -> None:
    messages = [
        ModelResponse(
            parts=[
                ThinkingPart(content="full thinking trace", provider_name="test"),
                ToolCallPart(tool_name="lookup", args={"query": "x"}, tool_call_id="call-1"),
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
    assert parts[1]["type"] == "tool_call"
    assert parts[2]["type"] == "tool_return"
    assert parts[2]["content"] == "x" * 100
    assert parts[2]["original_char_count"] == 140
    assert parts[2]["truncated"] is True


def test_llm_visible_dump_omits_skip_json_schema_fields_and_usage_tracks_tools() -> None:
    dumped = llm_visible_dump(_result(q3_drivers=(True, False)))

    assert "id" not in dumped
    assert "cost" not in dumped
    assert "image_cost" not in dumped
    assert "latency" not in dumped
    assert "ground_truth" not in dumped
    assert "extras" not in dumped
    assert "help_text" not in dumped["questions"][0]
    sub_question = dumped["questions"][2]["sub_questions"][0]
    assert "answer" not in sub_question
    assert "help_text" not in sub_question

    usage = usage_to_dict(RunUsage(input_tokens=5, output_tokens=7, requests=1), tool_calls=2)
    assert usage["tool_calls"] == 2
    assert usage["total_tokens"] == 12


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


def test_audit_balanced_sampler_prioritizes_outcome_spread() -> None:
    instances = [
        _instance("meet-1", _result(outcome="Meets")),
        _instance("meet-2", _result(q1_answer="No", outcome="Meets")),
        _instance("dnm-1", _result(q2_answer="No", outcome="Does Not Meet")),
        _instance("dnm-2", _result(q3_answer="No", outcome="Does Not Meet")),
    ]
    sampler = AuditBalancedBatchSampler(minibatch_size=2, reference_policy="prefer_r2")

    ids = sampler.next_minibatch_ids(ListDataLoader(instances), _SamplerState(i=0))
    outcomes = {instances[item_id].references[0][1].overall_outcome for item_id in ids}

    assert outcomes == {"Meets", "Does Not Meet"}


def test_audit_balanced_sampler_uses_question_mix_after_outcome_spread() -> None:
    instances = [
        _instance("all-yes", _result(outcome="Meets")),
        _instance("q1-no", _result(q1_answer="No", outcome="Meets")),
        _instance("q2-no", _result(q2_answer="No", outcome="Meets")),
    ]
    sampler = AuditBalancedBatchSampler(minibatch_size=2, reference_policy="prefer_r2")

    ids = sampler.next_minibatch_ids(ListDataLoader(instances), _SamplerState(i=0))
    question_values: dict[str, set[str]] = {}
    for item_id in ids:
        result = instances[item_id].references[0][1]
        for question in result.questions:
            question_values.setdefault(question.id, set()).add(question.answer)

    assert any(question_values.get(question_id) == {"Yes", "No"} for question_id in ("Q1", "Q2"))


def test_audit_balanced_sampler_rotates_when_labels_do_not_help() -> None:
    instances = [_instance(f"case-{index}", _result(outcome="Meets")) for index in range(6)]
    sampler = AuditBalancedBatchSampler(minibatch_size=3, reference_policy="prefer_r2")
    loader = ListDataLoader(instances)

    first_ids = set(sampler.next_minibatch_ids(loader, _SamplerState(i=0)))
    second_ids = set(sampler.next_minibatch_ids(loader, _SamplerState(i=1)))

    assert first_ids.isdisjoint(second_ids)


def test_runner_translates_audit_balanced_sampler_minibatch_size() -> None:
    request = OptimizationRunCreate(
        name="sampler translation",
        form_id="demo",
        form_version="v0.1",
        gepa_params=OptimizationGepaParams(
            max_metric_calls=10,
            batch_sampler="audit_balanced",
            reflection_minibatch_size=5,
        ),
        case_splits=[
            {"case_id": "case-1", "split": "train"},
            {"case_id": "case-2", "split": "val"},
        ],
    )

    sampler, reflection_minibatch_size = OptimizationRunService()._batch_sampler_for(request)

    assert isinstance(sampler, AuditBalancedBatchSampler)
    assert sampler.minibatch_size == 5
    assert reflection_minibatch_size is None


def test_gepa_budget_modes_are_mutually_exclusive() -> None:
    assert OptimizationGepaParams(max_metric_calls=10).max_metric_calls == 10
    assert OptimizationGepaParams(max_metric_calls=10).batch_sampler == "audit_balanced"
    assert (
        OptimizationGepaParams(max_metric_calls=10, batch_sampler="epoch_shuffled").batch_sampler
        == "epoch_shuffled"
    )
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
    assert auto_budget(num_candidates=6, valset_size=4) == 396
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


class _SamplerState:
    def __init__(self, i: int) -> None:
        self.i = i


def _test_model_config():
    from app.core.llm import LLMModelAPI, LLMModelConfig

    return LLMModelConfig(model_name="test", api=LLMModelAPI.TEST)
