"""Shared Monty collection types, constants, and helpers."""

from __future__ import annotations

import inspect
import json
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal

import pandas as pd
import plotly.express as px

from app.capabilities.monty.usage import UsageTracker
from app.core.config import Settings
from app.models.chat_state import TFRChatState
from app.services.chat_artifacts import ChatArtifactStore, dataframe_preview

FilterOperator = Literal["==", "!=", ">", ">=", "<", "<=", "contains", "in", "isna", "notna"]
PLOTLY_COLORWAY = list(reversed(px.colors.sequential.Viridis))
PLOTLY_CONTINUOUS_SCALE = "Viridis_r"
BAR_PROTECTED_KEYS = {"data_frame", "x", "y", "color", "title"}
LINE_PROTECTED_KEYS = {"data_frame", "x", "y", "color", "title"}
SCATTER_PROTECTED_KEYS = {"data_frame", "x", "y", "color", "title"}
HISTOGRAM_PROTECTED_KEYS = {"data_frame", "x", "color", "title", "nbins"}
BOX_PROTECTED_KEYS = {"data_frame", "x", "y", "color", "title"}
PIE_PROTECTED_KEYS = {"data_frame", "names", "values", "title"}
LAYOUT_KWARGS_HELP = (
    "Any JSON-safe Figure.update_layout key is accepted; common useful keys include "
    "xaxis_title, yaxis_title, showlegend, legend, margin, hovermode, template, "
    "height, and width."
)


def _allowed_plotly_kwargs(
    plotly_func: Callable[..., Any],
    protected_keys: set[str],
) -> tuple[str, ...]:
    return tuple(
        name for name in inspect.signature(plotly_func).parameters if name not in protected_keys
    )


PLOTLY_KWARGS_BY_TOOL: dict[str, tuple[str, ...]] = {
    "create_bar_chart": _allowed_plotly_kwargs(px.bar, BAR_PROTECTED_KEYS),
    "create_line_chart": _allowed_plotly_kwargs(px.line, LINE_PROTECTED_KEYS),
    "create_scatter_plot": _allowed_plotly_kwargs(px.scatter, SCATTER_PROTECTED_KEYS),
    "create_histogram": _allowed_plotly_kwargs(px.histogram, HISTOGRAM_PROTECTED_KEYS),
    "create_box_plot": _allowed_plotly_kwargs(px.box, BOX_PROTECTED_KEYS),
    "create_pie_chart": _allowed_plotly_kwargs(px.pie, PIE_PROTECTED_KEYS),
}


def _as_column_list(value: list[str] | str, *, argument_name: str) -> list[str]:
    columns = [value] if isinstance(value, str) else list(value)
    if not columns or any(not isinstance(column, str) or not column for column in columns):
        raise ValueError(f"{argument_name} must be a non-empty column name or list of names.")
    return columns


def _require_columns(dataframe: pd.DataFrame, columns: list[str]) -> None:
    missing = [column for column in columns if column not in dataframe.columns]
    if missing:
        raise ValueError(f"Unknown dataset column(s): {', '.join(missing)}")


def _require_output_columns(
    *,
    existing_columns: pd.Index,
    output_columns: list[str],
    preserved_columns: list[str],
) -> None:
    if any(not column for column in output_columns):
        raise ValueError("Output column names cannot be empty.")
    conflicts = sorted(set(output_columns) & set(preserved_columns))
    if conflicts:
        raise ValueError(
            "Output column name(s) conflict with preserved columns: " + ", ".join(conflicts)
        )
    existing_names = {str(column) for column in existing_columns}
    existing_conflicts = sorted(set(output_columns) & existing_names)
    if existing_conflicts:
        raise ValueError(
            "Output column name(s) already exist in the input dataset: "
            + ", ".join(existing_conflicts)
        )


def _handle_from_preview(value: Any, *, argument_name: str, expected_prefix: str) -> str:
    if isinstance(value, str) and value:
        return value
    if isinstance(value, dict):
        handle = value.get("handle")
        if isinstance(handle, str) and handle.startswith(expected_prefix):
            return handle
        raise TypeError(
            f"{argument_name} must be a handle string like {expected_prefix!r}. "
            "Preview dictionaries must include a valid 'handle' field."
        )
    raise TypeError(
        f"{argument_name} must be a handle string like {expected_prefix!r}. "
        "preview_dataset() returns a preview dictionary; prefer passing the original "
        "handle string directly to transform and chart tools."
    )


def _dataset_handle(value: Any, *, argument_name: str = "dataset_handle") -> str:
    return _handle_from_preview(value, argument_name=argument_name, expected_prefix="ds_")


def _chart_handle(value: Any, *, argument_name: str = "chart_handle") -> str:
    return _handle_from_preview(value, argument_name=argument_name, expected_prefix="fig_")


def _merge_plotly_kwargs(
    plotly_kwargs: dict[str, Any] | None,
    extra_plotly_kwargs: dict[str, Any],
) -> dict[str, Any] | None:
    merged = dict(plotly_kwargs or {})
    overlap = sorted(set(merged) & set(extra_plotly_kwargs))
    if overlap:
        raise ValueError(
            "Plotly option(s) were supplied both directly and in plotly_kwargs: "
            + ", ".join(overlap)
        )
    merged.update(extra_plotly_kwargs)
    return merged or None


def _format_handle_description(metadata: dict[str, Any]) -> str:
    handle = str(metadata.get("handle") or "")
    kind = str(metadata.get("kind") or "artifact")
    parts = [f"{handle}: {kind}"] if handle else [kind]
    label = str(metadata.get("label") or "")
    if label:
        parts.append(f"label={label!r}")
    row_count = metadata.get("row_count")
    column_count = metadata.get("column_count")
    if row_count is not None and column_count is not None:
        parts.append(f"shape={row_count}x{column_count}")
    source = str(metadata.get("source") or "")
    if source:
        parts.append(f"source={source}")
    columns = metadata.get("columns")
    if isinstance(columns, list) and columns:
        parts.append("columns=" + ", ".join(str(column) for column in columns))
    return "; ".join(parts)


def _format_dataset_description(dataset: Any, *, limit: int) -> str:
    preview = dataframe_preview(dataset, limit=limit)
    label = f"\nLabel: {dataset.label}" if dataset.label else ""
    rows = [
        "- " + json.dumps(row, ensure_ascii=False, sort_keys=True)
        for row in preview["preview_rows"]
    ]
    row_text = "\n".join(rows) if rows else "- No preview rows"
    return (
        f"Dataset handle: {dataset.handle}"
        f"{label}\n"
        f"Shape: {dataset.row_count} row(s) x {dataset.column_count} column(s)\n"
        f"Columns: {', '.join(dataset.columns)}\n"
        f"Preview rows (first {len(preview['preview_rows'])} of {dataset.row_count}):\n"
        f"{row_text}"
    )


@dataclass(slots=True)
class MontyRuntimeContext:
    state: TFRChatState
    settings: Settings
    rlm_usage: UsageTracker = field(default_factory=UsageTracker)
    rlm_call_count: int = 0
    rlm_lock: threading.Lock = field(default_factory=threading.Lock)

    @property
    def store(self) -> ChatArtifactStore:
        return ChatArtifactStore(self.settings)

    def reset_rlm_tracking(self) -> None:
        with self.rlm_lock:
            self.rlm_call_count = 0
            self.rlm_usage.reset()

    def reserve_rlm_calls(self, count: int, *, max_calls: int) -> None:
        if count < 1:
            return
        with self.rlm_lock:
            if self.rlm_call_count + count > max_calls:
                raise RuntimeError(
                    f"LLM call limit exceeded: {self.rlm_call_count} + {count} > "
                    f"{max_calls}. Use Python code for aggregation or split work into "
                    "fewer sub-LLM calls."
                )
            self.rlm_call_count += count

    def rlm_tracking_payload(self) -> dict[str, Any]:
        with self.rlm_lock:
            call_count = self.rlm_call_count
        return {
            "call_count": call_count,
            "max_llm_calls": self.settings.monty_rlm_max_llm_calls,
            "usage": self.rlm_usage.as_dict(),
        }
