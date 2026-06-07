from __future__ import annotations

import logging
import time
from typing import Any

from gepa.core.adapter import EvaluationBatch
from pydantic_ai import Agent
from pydantic_ai.messages import ModelMessage

from app.agents.review_agent import (
    REVIEW_USER_PROMPT,
    FileReviewAgentDeps,
)
from app.core.llm import LLMModelConfig, build_llm_model
from app.models.audit import AuditFormResult, AuditFormWithFinancialsResult, AuditResult
from app.schemas.optimizations import OptimizationRunCreate, OptimizationTraceConfig
from app.services.optimization.artifacts import OptimizationArtifactWriter
from app.services.optimization.components import AuditPromptProgram
from app.services.optimization.metrics import JudgeFeedback, compare_and_score, select_references
from app.services.optimization.models import (
    OptimizationDataInstance,
    OptimizationRolloutOutput,
    OptimizationTrajectory,
)
from app.services.optimization.reflection import propose_new_texts
from app.services.optimization.traces import count_tool_calls, serialize_messages
from app.services.optimization.utils import json_hash, llm_visible_dump, merge_usage, usage_to_dict

logger = logging.getLogger(__name__)


class TFRGepaAdapter:
    def __init__(
        self,
        *,
        agent: Any,
        config: OptimizationRunCreate,
        trace_config: OptimizationTraceConfig,
        artifact_writer: OptimizationArtifactWriter,
        proposer_model_config: LLMModelConfig,
        judge_model_config: LLMModelConfig | None,
    ) -> None:
        self.agent = agent
        self.config = config
        self.trace_config = trace_config
        self.artifact_writer = artifact_writer
        self.proposer_model_config = proposer_model_config
        self.judge_model_config = judge_model_config
        self.token_usage: dict[str, int] = {}

    def evaluate(
        self,
        batch: list[OptimizationDataInstance],
        candidate: dict[str, str],
        capture_traces: bool = False,
    ) -> EvaluationBatch[OptimizationTrajectory, OptimizationRolloutOutput]:
        outputs: list[OptimizationRolloutOutput] = []
        scores: list[float] = []
        trajectories: list[OptimizationTrajectory] | None = [] if capture_traces else None
        with AuditPromptProgram(candidate).apply_to(self.agent):
            for instance in batch:
                output, score, trajectory = self._run_instance(
                    instance,
                    candidate,
                    capture_traces=capture_traces or self.trace_config.capture_traces,
                )
                outputs.append(output)
                scores.append(score)
                if trajectories is not None:
                    trajectories.append(trajectory)
        return EvaluationBatch(outputs=outputs, scores=scores, trajectories=trajectories)

    def _run_instance(
        self,
        instance: OptimizationDataInstance,
        candidate: dict[str, str],
        *,
        capture_traces: bool,
    ) -> tuple[OptimizationRolloutOutput, float, OptimizationTrajectory]:
        started = time.perf_counter()
        messages: list[ModelMessage] = []
        usage: dict[str, int] = {}
        result_model: AuditResult | None = None
        error_message: str | None = None
        try:
            deps = FileReviewAgentDeps(
                path_to_questionnaire=instance.form_path,
                claim_number=instance.claim_number,
                effective_date=instance.effective_date or "",
                runtime_context="",
                tools=list(instance.tools),
                knowledge_docs=list(instance.knowledge_docs),
            )
            output_type = (
                AuditFormWithFinancialsResult
                if deps.canonical.form_kind == "financial"
                else AuditFormResult
            )
            result = self.agent.run_sync(
                user_prompt=REVIEW_USER_PROMPT,
                deps=deps,
                output_type=output_type,
            )
            messages = result.new_messages()
            tool_calls = count_tool_calls(messages)
            merge_usage(self.token_usage, result.usage(), tool_calls=tool_calls)
            usage = usage_to_dict(result.usage(), tool_calls=tool_calls)
            result_model = result.output
        except Exception as exc:
            logger.exception("Optimization rollout failed for case %s", instance.case_id)
            error_message = str(exc)

        score, feedback, comparison = self._score(instance, result_model, error_message)
        elapsed = time.perf_counter() - started
        rollout = OptimizationRolloutOutput(
            result=result_model,
            success=result_model is not None and error_message is None,
            error_message=error_message,
            comparison=comparison,
            feedback=feedback,
            usage=usage,
        )
        serialized_messages = (
            serialize_messages(messages, self.trace_config)
            if capture_traces and self.trace_config.include_debug_traces
            else []
        )
        final_output = llm_visible_dump(result_model) if result_model is not None else None
        reflection_trace = {
            "case_id": instance.case_id,
            "claim_number": instance.claim_number,
            "prompt": REVIEW_USER_PROMPT,
            "candidate_hash": json_hash(candidate),
            "generated_output": final_output,
            "error": error_message,
            "elapsed_seconds": elapsed,
            "usage": usage,
        }
        if serialized_messages:
            reflection_trace["messages"] = serialized_messages
        trajectory = OptimizationTrajectory(
            case_id=instance.case_id,
            messages=serialized_messages,
            reflection_trace=reflection_trace,
            final_output=final_output,
            error=error_message,
            feedback=feedback,
            score=score,
            usage=usage,
        )
        if capture_traces:
            self.artifact_writer.append_trace(
                {
                    "case_id": instance.case_id,
                    "split": instance.split,
                    "candidate": candidate,
                    "score": score,
                    "feedback": feedback,
                    "trajectory": reflection_trace,
                }
            )
        return rollout, score, trajectory

    def _score(
        self,
        instance: OptimizationDataInstance,
        generated: AuditResult | None,
        error_message: str | None,
    ) -> tuple[float, str, dict[str, Any]]:
        if generated is None:
            feedback = f"Rollout failed: {error_message or 'No output'}"
            return 0.0, feedback, {"score": 0.0, "error": error_message}

        selected_references = select_references(instance.references, self.config.reference_policy)
        if not selected_references:
            return 0.0, "No reference result available for this case.", {"score": 0.0}

        scored: list[tuple[float, str, dict[str, Any]]] = []
        for reference_kind, reference in selected_references:
            score, feedback, comparison = compare_and_score(
                generated,
                reference,
                score_key=self.config.score_key,
            )
            scored.append((score, f"Reference {reference_kind}\n{feedback}", comparison))

        deterministic_score = sum(item[0] for item in scored) / len(scored)
        feedback = "\n\n".join(item[1] for item in scored)
        prior_feedback = self._prior_feedback_text(instance)
        if prior_feedback:
            feedback = f"{feedback}\n\nPrior user feedback:\n{prior_feedback}"
        comparison = {
            "score": deterministic_score,
            "deterministic_score": deterministic_score,
            "references": [item[2] for item in scored],
        }
        if prior_feedback:
            comparison["prior_feedback"] = prior_feedback
        if self.config.metric_mode == "comparison_with_judge":
            judge_feedback, judge_score = self._judge_feedback(
                generated,
                selected_references[0][1],
                feedback,
                prior_feedback=prior_feedback,
            )
            final_score = deterministic_score
            judge_weight = self.config.judge_score_weight
            if judge_score is not None and judge_weight > 0:
                final_score = (deterministic_score * (1 - judge_weight)) + (
                    judge_score * judge_weight
                )
            feedback = f"{feedback}\n\nLLM judge feedback:\n{judge_feedback}"
            if judge_score is not None:
                feedback = (
                    f"{feedback}\n\nJudge score `{judge_score:.4f}` blended with "
                    f"deterministic score `{deterministic_score:.4f}` at weight "
                    f"`{judge_weight:.2f}` => final score `{final_score:.4f}`."
                )
            comparison["score"] = final_score
            comparison["judge_feedback"] = judge_feedback
            comparison["judge_score"] = judge_score
            comparison["judge_score_weight"] = judge_weight
            comparison["final_score"] = final_score
        return float(comparison["score"]), feedback, comparison

    def _prior_feedback_text(self, instance: OptimizationDataInstance) -> str:
        if not self.config.use_feedback_when_available:
            return ""
        feedback = instance.metadata.get("feedback")
        if not isinstance(feedback, dict):
            return ""
        parts: list[str] = []
        comments = feedback.get("comments")
        if isinstance(comments, list):
            parts.extend(str(comment).strip() for comment in comments if str(comment).strip())
        latest_comment = feedback.get("latest_comment")
        if isinstance(latest_comment, str) and latest_comment.strip():
            latest = latest_comment.strip()
            if latest not in parts:
                parts.append(latest)
        return "\n".join(f"- {part}" for part in parts)

    def _judge_feedback(
        self,
        generated: AuditResult,
        reference: AuditResult,
        comparison_feedback: str,
        *,
        prior_feedback: str = "",
    ) -> tuple[str, float | None]:
        if self.judge_model_config is None:
            return "Judge feedback requested but no judge model was configured.", None
        try:
            agent = Agent(
                build_llm_model(self.judge_model_config),
                output_type=JudgeFeedback,
                instructions=(
                    "Compare generated and reference audit questionnaire outputs. "
                    "Return concise prompt-improvement feedback and an optional "
                    "judge_score from 0 to 1. If prior user feedback is provided, "
                    "evaluate whether the generated output respects feedback that "
                    "is applicable to this case. Include feedback-related findings "
                    "in the feedback field, and include them in missed_rules or "
                    "overfit_risks when they apply. Prior feedback may come from an "
                    "independent earlier generation, so penalize only repeated or "
                    "contradictory issues that are relevant to this generated result."
                ),
            )
            prompt = (
                "Generated questionnaire:\n"
                f"{str(generated)}\n\nReference questionnaire:\n{str(reference)}\n\n"
                f"Deterministic comparison:\n{comparison_feedback}"
            )
            if prior_feedback:
                prompt = f"{prompt}\n\nPrior user feedback:\n{prior_feedback}"
            result = agent.run_sync(prompt)
            merge_usage(self.token_usage, result.usage())
            judge = result.output
            parts = [judge.feedback]
            if judge.missed_rules:
                parts.append("Missed rules: " + "; ".join(judge.missed_rules))
            if judge.overfit_risks:
                parts.append("Overfit risks: " + "; ".join(judge.overfit_risks))
            if judge.judge_score is not None:
                parts.append(f"Judge score: {judge.judge_score:.4f}")
            return "\n".join(parts), judge.judge_score
        except Exception as exc:
            logger.exception("LLM judge failed")
            return f"LLM judge failed: {exc}", None

    def make_reflective_dataset(
        self,
        candidate: dict[str, str],
        eval_batch: EvaluationBatch[OptimizationTrajectory, OptimizationRolloutOutput],
        components_to_update: list[str],
    ) -> dict[str, list[dict[str, Any]]]:
        records: list[dict[str, Any]] = []
        for trajectory, output, score in zip(
            eval_batch.trajectories or [],
            eval_batch.outputs,
            eval_batch.scores,
            strict=True,
        ):
            feedback_text = output.feedback or trajectory.feedback or ""
            if not feedback_text:
                if score >= 0.8:
                    feedback_text = "Good response"
                elif score >= 0.5:
                    feedback_text = "Adequate response, could be improved"
                else:
                    feedback_text = f"Poor response (score: {score:.2f})"
                    if output.error_message:
                        feedback_text += f" - Error: {output.error_message}"

            records.append(
                {
                    "case_id": trajectory.case_id,
                    "instructions": candidate.get("instructions", ""),
                    "score": score,
                    "success": output.success,
                    "error_message": output.error_message,
                    "feedback": feedback_text,
                    "trace": trajectory.reflection_trace,
                }
            )
        return {"traces": records}

    def propose_new_texts(
        self,
        candidate: dict[str, str],
        reflective_dataset: dict[str, list[dict[str, Any]]],
        components_to_update: list[str],
    ) -> dict[str, str]:
        signature_result = propose_new_texts(
            candidate,
            reflective_dataset,
            components_to_update,
            self.proposer_model_config,
        )
        merge_usage(self.token_usage, signature_result.usage())
        return {
            component.component_name: component.optimized_value.strip()
            for component in signature_result.output.updated_components
            if component.component_name in components_to_update
        }
