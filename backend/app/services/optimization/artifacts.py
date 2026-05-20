from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.services.optimization.utils import json_safe, now_utc


class OptimizationArtifactWriter:
    def __init__(self, run_id: str, root_dir: Path) -> None:
        self.run_id = run_id
        self.run_dir = root_dir / run_id
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.events_path = self.run_dir / "events.jsonl"
        self.traces_path = self.run_dir / "traces.jsonl"
        self.dag_path = self.run_dir / "dag.json"
        self.native_html_path = self.run_dir / "gepa-native.html"
        self.report_path = self.run_dir / "final-report.json"
        self.cancel_path = self.run_dir / "cancel.requested"
        self._event_sequence = 0

    def request_cancel(self) -> None:
        self.cancel_path.write_text("cancel requested", encoding="utf-8")

    def is_cancel_requested(self) -> bool:
        return self.cancel_path.exists()

    def append_event(
        self,
        event_type: str,
        message: str,
        *,
        iteration: int | None = None,
        level: str = "info",
        data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self._event_sequence += 1
        payload = {
            "id": str(uuid4()),
            "run_id": self.run_id,
            "sequence": self._event_sequence,
            "type": event_type,
            "message": message,
            "iteration": iteration,
            "level": level,
            "data": json_safe(data or {}),
            "created_at": now_utc().isoformat(),
        }
        with self.events_path.open("a", encoding="utf-8") as file_obj:
            file_obj.write(json.dumps(payload, ensure_ascii=True, default=str))
            file_obj.write("\n")
        return payload

    def append_trace(self, trace: dict[str, Any]) -> None:
        with self.traces_path.open("a", encoding="utf-8") as file_obj:
            file_obj.write(json.dumps(json_safe(trace), ensure_ascii=True, default=str))
            file_obj.write("\n")

    def write_json(self, path: Path, payload: Any) -> None:
        path.write_text(json.dumps(json_safe(payload), indent=2, default=str), encoding="utf-8")

    def write_text(self, path: Path, payload: str) -> None:
        path.write_text(payload, encoding="utf-8")

    def artifact_map(self) -> dict[str, str]:
        return {
            "events": str(self.events_path),
            "traces": str(self.traces_path),
            "dag": str(self.dag_path),
            "native_html": str(self.native_html_path),
            "final_report": str(self.report_path),
        }


class OptimizationRunCallback:
    def __init__(self, writer: OptimizationArtifactWriter) -> None:
        self.writer = writer

    def _emit(self, event_type: str, event: dict[str, Any], message: str) -> None:
        self.writer.append_event(
            event_type,
            message,
            iteration=event.get("iteration") if isinstance(event.get("iteration"), int) else None,
            data=event,
        )

    def on_optimization_start(self, event: dict[str, Any]) -> None:
        self._emit(
            "run_started",
            event,
            (
                f"GEPA optimization started ({event.get('trainset_size')} train, "
                f"{event.get('valset_size')} val)"
            ),
        )

    def on_optimization_end(self, event: dict[str, Any]) -> None:
        self._emit(
            "run_completed",
            event,
            f"GEPA optimization completed after {event.get('total_iterations')} iterations",
        )

    def on_iteration_start(self, event: dict[str, Any]) -> None:
        self._emit("iteration_started", event, f"Iteration {event.get('iteration')} started")

    def on_iteration_end(self, event: dict[str, Any]) -> None:
        accepted = "accepted" if event.get("proposal_accepted") else "rejected"
        self._emit(
            "iteration_completed",
            event,
            f"Iteration {event.get('iteration')} completed ({accepted})",
        )

    def on_candidate_selected(self, event: dict[str, Any]) -> None:
        self._emit(
            "candidate_selected",
            event,
            f"Selected candidate {event.get('candidate_idx')} for mutation",
        )

    def on_minibatch_sampled(self, event: dict[str, Any]) -> None:
        self._emit("minibatch_sampled", event, "Sampled training examples")

    def on_evaluation_start(self, event: dict[str, Any]) -> None:
        self._emit("evaluation_started", event, "Evaluating candidate")

    def on_evaluation_end(self, event: dict[str, Any]) -> None:
        scores = event.get("scores") or []
        average = sum(scores) / len(scores) if scores else None
        suffix = f" (avg {average:.4f})" if average is not None else ""
        self._emit("evaluation_completed", event, f"Evaluation completed{suffix}")

    def on_evaluation_skipped(self, event: dict[str, Any]) -> None:
        self._emit("evaluation_skipped", event, f"Evaluation skipped: {event.get('reason')}")

    def on_valset_evaluated(self, event: dict[str, Any]) -> None:
        self._emit(
            "validation_evaluated",
            event,
            f"Validation score {event.get('average_score', 0):.4f}",
        )

    def on_reflective_dataset_built(self, event: dict[str, Any]) -> None:
        self._emit("reflective_dataset_built", event, "Built reflective dataset")

    def on_proposal_start(self, event: dict[str, Any]) -> None:
        self._emit("proposal_started", event, "Proposing prompt update")

    def on_proposal_end(self, event: dict[str, Any]) -> None:
        self._emit("proposal_created", event, "Created prompt proposal")

    def on_candidate_accepted(self, event: dict[str, Any]) -> None:
        self._emit(
            "candidate_accepted",
            event,
            f"Accepted candidate {event.get('new_candidate_idx')}",
        )

    def on_candidate_rejected(self, event: dict[str, Any]) -> None:
        self._emit("candidate_rejected", event, "Rejected candidate")

    def on_merge_attempted(self, event: dict[str, Any]) -> None:
        self._emit("merge_attempted", event, "Attempted candidate merge")

    def on_merge_accepted(self, event: dict[str, Any]) -> None:
        self._emit("merge_accepted", event, "Accepted merged candidate")

    def on_merge_rejected(self, event: dict[str, Any]) -> None:
        self._emit("merge_rejected", event, "Rejected candidate merge")

    def on_pareto_front_updated(self, event: dict[str, Any]) -> None:
        self._emit("pareto_front_updated", event, "Pareto front updated")

    def on_state_saved(self, event: dict[str, Any]) -> None:
        self._emit("state_saved", event, "GEPA state saved")

    def on_budget_updated(self, event: dict[str, Any]) -> None:
        used = event.get("metric_calls_used")
        remaining = event.get("metric_calls_remaining")
        if isinstance(used, int) and isinstance(remaining, int):
            message = f"Metric budget {used}/{used + remaining}"
        elif isinstance(used, int):
            message = f"Metric budget used {used}"
        else:
            message = "Metric budget updated"
        self._emit("budget_updated", event, message)

    def on_error(self, event: dict[str, Any]) -> None:
        self.writer.append_event(
            "run_error",
            str(event.get("exception") or "Optimization error"),
            level="error",
            data=event,
        )


class CancelFileStopper:
    def __init__(self, writer: OptimizationArtifactWriter) -> None:
        self.writer = writer

    def __call__(self, _gepa_state: Any) -> bool:
        return self.writer.is_cancel_requested()
