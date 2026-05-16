"""TFR-specific Monty helper collections."""

from __future__ import annotations

import asyncio
import inspect
import json
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal

import pandas as pd
import plotly.express as px
import plotly.io as pio
from pydantic_ai import Agent
from pydantic_ai.models.test import TestModel

from app.core.config import Settings
from app.models.chat_state import TFRChatState
from app.presenters.a2ui import generate_data_table, generate_plotly_chart
from app.services.chat_artifacts import ChatArtifactStore, dataframe_preview

from .registry import FunctionRegistry, ToolArgument, ToolCollection, ToolSpec, tool
from .usage import UsageTracker

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
DEFAULT_RLM_BATCH_SIZE = 12
DEFAULT_RLM_PROMPT_CHARS = 200_000
DEFAULT_RLM_MAX_LLM_CALLS = 24


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
        "handle string directly to transform and chart helpers."
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
            "max_llm_calls": int(
                getattr(self.settings, "monty_rlm_max_llm_calls", DEFAULT_RLM_MAX_LLM_CALLS)
            ),
            "usage": self.rlm_usage.as_dict(),
        }


class HandlesCollection(ToolCollection):
    """Discover and emit file-backed chat handles."""

    name = "handles"
    description = (
        "List and describe dataset/chart handles, preview dataset metadata only when code "
        "needs a dict, and emit handled artifacts into the chat UI. Monty helpers consume "
        "handle strings; they do not load SQL tables or dataframe objects into variables."
    )

    def __init__(self, context: MontyRuntimeContext) -> None:
        self.context = context

    @tool
    def describe_handles(self) -> str:
        """Return a compact text inventory of available dataset and chart handles.

        Prefer this over list_handles() when the next step is deciding which
        handle string to pass into dataframe or visualization helpers. Dataset
        handles usually come from SQL execute(..., persist_result=True) or from
        Monty transforms such as group_by(), value_counts(), and put_dataset().

        Returns:
            str: Human-readable handle inventory.

        Examples:
            ```python
            summary = describe_handles()
            print(summary)
            # Prints
            # ds_1: dataset; label='Claim notes'; shape=125x3; source=sql
            # columns=claim_id, status, amount
            # fig_1: plotly_chart; label='Claims by status'
            ```
        """
        if not self.context.state.handles:
            return (
                "No dataset or chart handles are available. Use SQL execute with "
                "persist_result=true to create a dataset handle from database rows, or "
                "create one in Monty with put_dataset()."
            )
        return "\n".join(
            _format_handle_description(handle.model_dump()) for handle in self.context.state.handles
        )

    @tool
    def list_handles(self) -> list[dict[str, Any]]:
        """List dataset and chart handles available in this chat session.

        This is a low-level structured helper. Prefer describe_handles() when a
        string summary is enough. Pass dataset handle strings such as "ds_1"
        directly to dataframe and chart helpers.

        Returns:
            list[dict[str, Any]]: Handle metadata including kind, label, row count,
            column count, and source where available.

        Examples:
            ```python
            handles = list_handles()
            print(handles)
            # Prints a list similar to:
            # [
            #     {"handle": "ds_1", "kind": "dataset", "label": "Claim notes"},
            #     {"handle": "fig_1", "kind": "plotly_chart", "label": "Counts"},
            # ]
            ```
        """
        return [handle.model_dump() for handle in self.context.state.handles]

    @tool
    def describe_handle(self, handle: str) -> str:
        """Return a compact text summary for one dataset or chart handle.

        Prefer this over inspect_handle() when a string summary is enough.

        Args:
            handle: Dataset or chart handle to describe.

        Returns:
            str: Human-readable handle summary.

        Examples:
            ```python
            summary = describe_handle("ds_1")
            print(summary)
            # Prints
            # ds_1: dataset; label='Claims'; shape=125x3; source=sql
            # columns=claim_id, status, amount
            ```
        """
        metadata = self.context.store.inspect_handle(self.context.state, handle)
        return _format_handle_description(metadata)

    @tool
    def inspect_handle(self, handle: str) -> dict[str, Any]:
        """Inspect one stored dataset or chart handle.

        This is a low-level structured helper. Prefer describe_handle() when a
        string summary is enough.

        Args:
            handle: The dataset or chart handle to inspect.

        Returns:
            dict[str, Any]: Metadata for the requested handle.

        Examples:
            ```python
            details = inspect_handle("ds_1")
            print(details["kind"])
            print(details["columns"])
            # Prints
            # dataset
            # ["claim_id", "status", "amount"]
            ```
        """
        return self.context.store.inspect_handle(self.context.state, handle)

    def get_dataset(self, dataset_handle: str, *, limit: int = 10) -> dict[str, Any]:
        """Deprecated non-tool alias for preview_dataset()."""

        return self.preview_dataset(dataset_handle, limit=limit)

    @tool
    def describe_dataset(self, dataset_handle: str, *, limit: int = 5) -> str:
        """Return a text description and tiny preview for a dataset handle.

        Prefer this for inspection. It returns a string and keeps the durable
        dataset behind its handle. To source database rows for Monty, first call
        the SQL execute tool with persist_result=True, then pass the returned
        dataset_handle string directly to Monty helpers.

        Args:
            dataset_handle: Handle string such as "ds_1".
            limit: Maximum preview row count to include in the text summary.

        Returns:
            str: Human-readable dataset shape, columns, and preview rows.

        Examples:
            ```python
            dataset_handle = "ds_1"
            summary = describe_dataset(dataset_handle, limit=2)
            print(summary)
            # Prints
            # Dataset handle: ds_1
            # Shape: 125 row(s) x 3 column(s)
            # Columns: claim_id, status, amount
            # Preview rows (first 2 of 125):
            # - {"amount": 1200, "claim_id": "A1", "status": "open"}

            chart = create_bar_chart(dataset_handle, "status", "amount")
            ```
        """
        handle = _dataset_handle(dataset_handle)
        dataset = self.context.store.load_dataset(self.context.state, handle)
        return _format_dataset_description(dataset, limit=limit)

    @tool
    def preview_dataset(self, dataset_handle: str, *, limit: int = 10) -> dict[str, Any]:
        """Return structured preview metadata for a dataset handle.

        This is a low-level dict helper for code that must inspect columns,
        row_count, or preview_rows programmatically. Prefer describe_dataset()
        when a string summary is enough. This does not return a dataframe,
        complete dataset, or new handle. Do not build charts or transformed
        datasets from preview_rows because preview_rows may omit most of the
        dataset. For real transforms, pass the original handle string to helpers
        such as select_columns(), group_by(), melt_columns(), stack_metric_columns(),
        or create_bar_chart().

        Args:
            dataset_handle: Handle string such as "ds_1".
            limit: Maximum preview row count.

        Returns:
            dict[str, Any]: Dataset columns, row count, and preview records only.

        Examples:
            ```python
            dataset_handle = "ds_1"
            preview = preview_dataset(dataset_handle, limit=2)
            print(preview["columns"])
            print(preview["preview_rows"])
            # Prints
            # ["claim_id", "status", "amount"]
            # [{"claim_id": "A1", "status": "open", "amount": 1200}, ...]

            chart = create_bar_chart(dataset_handle, "status", "amount")
            ```
        """
        handle = _dataset_handle(dataset_handle)
        dataset = self.context.store.load_dataset(self.context.state, handle)
        return dataframe_preview(dataset, limit=limit)

    @tool
    def put_dataset(
        self,
        rows: list[dict[str, Any]],
        *,
        label: str = "",
    ) -> str:
        """Persist row dictionaries as a new dataset handle.

        Use this only for small datasets created inside Monty. For database
        rows, use the SQL execute tool with persist_result=True before entering
        Monty, then pass the returned dataset handle string directly to Monty
        helpers.

        Args:
            rows: Row records to persist. Keys become dataset columns.
            label: Optional human-readable label.

        Returns:
            str: New dataset handle.

        Examples:
            ```python
            rows = [
                {"status": "open", "count": 12},
                {"status": "closed", "count": 8},
            ]
            summary_handle = put_dataset(rows, label="Status counts")
            print(summary_handle)
            # Prints
            # ds_2
            ```
        """
        dataframe = pd.DataFrame(rows)
        artifact = self.context.store.save_dataframe(
            self.context.state,
            dataframe,
            label=label,
            source="monty",
        )
        return artifact.handle

    @tool
    def emit_table(
        self,
        dataset_handle: str,
        *,
        caption: str = "",
        max_rows: int = 200,
    ) -> dict[str, Any]:
        """Render a dataset handle as an inline chat table.

        Args:
            dataset_handle: Handle pointing to a stored dataset artifact.
            caption: Optional table caption.
            max_rows: Maximum rows to render in chat.

        Returns:
            dict[str, Any]: Emitted table metadata.

        Examples:
            ```python
            selected = select_columns("ds_1", ["claim_id", "status", "amount"])
            emitted = emit_table(selected, caption="Selected claim fields", max_rows=50)
            print(emitted["component"])
            print(emitted["rendered_rows"])
            # Prints
            # a2ui.DataTable
            # 50
            ```
        """
        handle = _dataset_handle(dataset_handle)
        dataset = self.context.store.load_dataset(self.context.state, handle)
        rows = dataset.rows[:max_rows]
        self.context.state.components.append(
            generate_data_table(
                headers=dataset.columns,
                rows=rows,
                caption=caption or dataset.label or f"Dataset {handle}",
                sortable=True,
            )
        )
        return {
            "component": "a2ui.DataTable",
            "dataset_handle": handle,
            "rendered_rows": len(rows),
            "row_count": dataset.row_count,
        }


class DataframeOperationsCollection(ToolCollection):
    """Create new dataset handles through common dataframe transforms."""

    name = "dataframe_operations"
    description = (
        "Transform full stored datasets referenced by handle strings into new dataset handles "
        "for EDA and visualization prep, including long-form and stacked-metric reshaping."
    )

    def __init__(self, context: MontyRuntimeContext) -> None:
        self.context = context

    def _load(self, dataset_handle: str) -> pd.DataFrame:
        handle = _dataset_handle(dataset_handle)
        return self.context.store.load_dataset(self.context.state, handle).to_dataframe()

    def _save(self, dataframe: pd.DataFrame, *, label: str, source: str) -> str:
        return self.context.store.save_dataframe(
            self.context.state,
            dataframe,
            label=label,
            source=source,
        ).handle

    @tool
    def select_columns(self, dataset_handle: str, columns: list[str]) -> str:
        """Select a subset of columns from a dataset.

        Args:
            dataset_handle: Input dataset handle.
            columns: Columns to keep in order.

        Returns:
            str: New dataset handle.

        Examples:
            ```python
            selected = select_columns("ds_1", ["claim_id", "status", "amount"])
            preview = preview_dataset(selected, limit=1)
            print(selected)
            print(preview["columns"])
            # Prints
            # ds_2
            # ["claim_id", "status", "amount"]
            ```
        """
        dataframe = self._load(dataset_handle)
        return self._save(
            dataframe.loc[:, columns],
            label="Selected columns",
            source="monty.select_columns",
        )

    @tool
    def filter_rows(
        self,
        dataset_handle: str,
        column: str,
        operator: FilterOperator,
        value: Any = None,
    ) -> str:
        """Filter rows with a single safe column comparison.

        Args:
            dataset_handle: Input dataset handle.
            column: Column to filter.
            operator: One of ==, !=, >, >=, <, <=, contains, in, isna, notna.
            value: Comparison value, or a list for the in operator.

        Returns:
            str: New dataset handle.

        Examples:
            ```python
            open_claims = filter_rows("ds_1", "status", "==", "open")
            preview = preview_dataset(open_claims, limit=2)
            print(open_claims)
            print(preview["row_count"])
            # Prints
            # ds_2
            # 42
            ```
        """
        dataframe = self._load(dataset_handle)
        series = dataframe[column]
        if operator == "==":
            mask = series == value
        elif operator == "!=":
            mask = series != value
        elif operator == ">":
            mask = series > value
        elif operator == ">=":
            mask = series >= value
        elif operator == "<":
            mask = series < value
        elif operator == "<=":
            mask = series <= value
        elif operator == "contains":
            mask = series.astype(str).str.contains(str(value), case=False, na=False)
        elif operator == "in":
            mask = series.isin(value if isinstance(value, list) else [value])
        elif operator == "isna":
            mask = series.isna()
        elif operator == "notna":
            mask = series.notna()
        else:
            raise ValueError(f"Unsupported filter operator: {operator}")
        return self._save(
            dataframe.loc[mask].reset_index(drop=True),
            label=f"Filtered {column} {operator}",
            source="monty.filter_rows",
        )

    @tool
    def sort_values(
        self,
        dataset_handle: str,
        columns: list[str] | str,
        *,
        ascending: bool = True,
    ) -> str:
        """Sort a dataset by one or more columns.

        Args:
            dataset_handle: Input dataset handle.
            columns: Column name or names to sort by.
            ascending: Whether to sort ascending.

        Returns:
            str: New dataset handle.

        Examples:
            ```python
            sorted_claims = sort_values("ds_1", "amount", ascending=False)
            preview = preview_dataset(sorted_claims, limit=1)
            print(sorted_claims)
            print(preview["preview_rows"][0]["amount"])
            # Prints
            # ds_2
            # 9800
            ```
        """
        sort_columns = [columns] if isinstance(columns, str) else columns
        dataframe = self._load(dataset_handle).sort_values(sort_columns, ascending=ascending)
        return self._save(
            dataframe.reset_index(drop=True),
            label="Sorted dataset",
            source="monty.sort_values",
        )

    @tool
    def group_by(
        self,
        dataset_handle: str,
        by: list[str] | str,
        aggregations: dict[str, str],
    ) -> str:
        """Aggregate rows by one or more grouping columns.

        Args:
            dataset_handle: Input dataset handle.
            by: Grouping column name or names.
            aggregations: Mapping of value column to aggregation such as count,
            sum, mean, min, max, or nunique.

        Returns:
            str: New aggregated dataset handle.

        Examples:
            ```python
            by_status = group_by("ds_1", "status", {"amount": "sum", "claim_id": "count"})
            preview = preview_dataset(by_status, limit=5)
            print(by_status)
            print(preview["columns"])
            # Prints
            # ds_2
            # ["status", "amount", "claim_id"]
            ```
        """
        group_columns = [by] if isinstance(by, str) else by
        dataframe = self._load(dataset_handle)
        grouped = dataframe.groupby(group_columns, dropna=False).agg(aggregations).reset_index()
        grouped.columns = [
            "__".join(part for part in column if part) if isinstance(column, tuple) else str(column)
            for column in grouped.columns
        ]
        return self._save(grouped, label="Grouped dataset", source="monty.group_by")

    @tool
    def melt_columns(
        self,
        dataset_handle: str,
        id_vars: list[str] | str,
        value_vars: list[str],
        *,
        var_name: str = "metric",
        value_name: str = "value",
    ) -> str:
        """Reshape full stored dataset columns from wide form to long form.

        Use this for multi-series or stacked bar preparation when several
        numeric metric columns should become rows with a metric label and value.
        This operates on the full stored dataset behind the handle; it does not
        use preview_dataset().preview_rows.

        Args:
            dataset_handle: Input dataset handle.
            id_vars: Column or columns to keep as identifiers, such as a category.
            value_vars: Metric/value columns to unpivot into rows.
            var_name: Name for the output metric-label column.
            value_name: Name for the output metric-value column.

        Returns:
            str: New long-form dataset handle.

        Examples:
            ```python
            long_metrics = melt_columns(
                "ds_1",
                "reference_policy",
                ["items_completed", "items_other"],
            )
            preview = preview_dataset(long_metrics, limit=2)
            print(long_metrics)
            print(preview["columns"])
            # Prints
            # ds_2
            # ["reference_policy", "metric", "value"]
            ```
        """
        dataframe = self._load(dataset_handle)
        id_columns = _as_column_list(id_vars, argument_name="id_vars")
        value_columns = _as_column_list(value_vars, argument_name="value_vars")
        _require_columns(dataframe, [*id_columns, *value_columns])
        _require_output_columns(
            existing_columns=dataframe.columns,
            output_columns=[var_name, value_name],
            preserved_columns=id_columns,
        )
        long = dataframe.melt(
            id_vars=id_columns,
            value_vars=value_columns,
            var_name=var_name,
            value_name=value_name,
        )
        return self._save(long, label="Long-form dataset", source="monty.melt_columns")

    @tool
    def stack_metric_columns(
        self,
        dataset_handle: str,
        category_columns: list[str] | str,
        metric_columns: list[str],
        *,
        metric_name: str = "metric",
        value_name: str = "value",
        aggfunc: Literal["sum", "mean", "count", "min", "max"] = "sum",
    ) -> str:
        """Prepare an aggregated long-form dataset for stacked bars.

        Use this when a dataset has one row per observation and several numeric
        metric columns, such as items_completed and items_other. The helper
        melts the full dataset to metric/value rows and aggregates duplicate
        category+metric pairs, so Plotly stacked bars render one segment per
        metric instead of many preview-row stripes.

        Args:
            dataset_handle: Input dataset handle.
            category_columns: Category column or columns for the bar x-axis.
            metric_columns: Numeric columns to stack.
            metric_name: Name for the output metric-label column.
            value_name: Name for the output metric-value column.
            aggfunc: Aggregation to apply for duplicate category+metric pairs.

        Returns:
            str: New aggregated long-form dataset handle with category columns,
            metric_name, and value_name columns.

        Examples:
            ```python
            stacked = stack_metric_columns(
                "ds_1",
                "reference_policy",
                ["items_completed", "items_other"],
            )
            chart = create_bar_chart(
                stacked,
                "reference_policy",
                "value",
                color="metric",
                title="Completed vs other by policy",
                plotly_kwargs={"barmode": "stack", "text_auto": True},
            )
            emitted = emit_plotly_chart(chart)
            print(emitted["component"])
            # Prints
            # a2ui.PlotlyChart
            ```
        """
        dataframe = self._load(dataset_handle)
        category_list = _as_column_list(category_columns, argument_name="category_columns")
        metric_list = _as_column_list(metric_columns, argument_name="metric_columns")
        _require_columns(dataframe, [*category_list, *metric_list])
        _require_output_columns(
            existing_columns=dataframe.columns,
            output_columns=[metric_name, value_name],
            preserved_columns=category_list,
        )

        long = dataframe.melt(
            id_vars=category_list,
            value_vars=metric_list,
            var_name=metric_name,
            value_name=value_name,
        )
        original_non_null = long[value_name].notna()
        numeric_values = pd.to_numeric(long[value_name], errors="coerce")
        if numeric_values[original_non_null].isna().any():
            raise ValueError("stack_metric_columns requires numeric metric columns.")
        long[value_name] = numeric_values
        grouped = (
            long.groupby([*category_list, metric_name], dropna=False, as_index=False)[value_name]
            .agg(aggfunc)
            .sort_values([*category_list, metric_name])
            .reset_index(drop=True)
        )
        return self._save(
            grouped,
            label="Stacked metric dataset",
            source="monty.stack_metric_columns",
        )

    @tool
    def value_counts(
        self,
        dataset_handle: str,
        column: str,
        *,
        top_n: int = 25,
    ) -> str:
        """Count the most common values in a column.

        Args:
            dataset_handle: Input dataset handle.
            column: Column to count.
            top_n: Maximum number of values to keep.

        Returns:
            str: New dataset handle with value and count columns.

        Examples:
            ```python
            counts = value_counts("ds_1", "status", top_n=10)
            chart = create_bar_chart(counts, "status", "count", title="Claims by status")
            emitted = emit_plotly_chart(chart)
            print(counts)
            print(emitted["component"])
            # Prints
            # ds_2
            # a2ui.PlotlyChart
            ```
        """
        counts = (
            self._load(dataset_handle)[column]
            .value_counts(dropna=False)
            .head(top_n)
            .rename_axis(column)
            .reset_index(name="count")
        )
        return self._save(counts, label=f"Value counts: {column}", source="monty.value_counts")

    @tool
    def pivot_table(
        self,
        dataset_handle: str,
        index: list[str] | str,
        values: str,
        *,
        columns: str | None = None,
        aggfunc: str = "count",
    ) -> str:
        """Create a simple pivot table.

        Args:
            dataset_handle: Input dataset handle.
            index: Row index column or columns.
            values: Value column to aggregate.
            columns: Optional pivoted column.
            aggfunc: Aggregation function such as count, sum, mean, min, or max.

        Returns:
            str: New dataset handle.

        Examples:
            ```python
            pivoted = pivot_table(
                "ds_1",
                index="region",
                columns="status",
                values="claim_id",
                aggfunc="count",
            )
            preview = preview_dataset(pivoted, limit=3)
            print(pivoted)
            print(preview["columns"])
            # Prints
            # ds_2
            # ["region", "closed", "open"]
            ```
        """
        pivot = pd.pivot_table(
            self._load(dataset_handle),
            index=index,
            columns=columns,
            values=values,
            aggfunc=aggfunc,
            fill_value=0,
        ).reset_index()
        pivot.columns = [str(column) for column in pivot.columns]
        return self._save(pivot, label="Pivot table", source="monty.pivot_table")

    @tool
    def bin_numeric(
        self,
        dataset_handle: str,
        column: str,
        *,
        bins: int = 10,
        strategy: Literal["quantile", "equal_width"] = "quantile",
        output_column: str = "",
    ) -> str:
        """Add a binned categorical column for a numeric value.

        Args:
            dataset_handle: Input dataset handle.
            column: Numeric column to bin.
            bins: Number of bins.
            strategy: quantile for qcut or equal_width for cut.
            output_column: Optional output column name.

        Returns:
            str: New dataset handle.

        Examples:
            ```python
            binned = bin_numeric("ds_1", "amount", bins=4, output_column="amount_band")
            counts = value_counts(binned, "amount_band")
            print(binned)
            print(preview_dataset(counts, limit=1)["columns"])
            # Prints
            # ds_2
            # ["amount_band", "count"]
            ```
        """
        dataframe = self._load(dataset_handle).copy()
        output = output_column or f"{column}_bin"
        numeric = pd.to_numeric(dataframe[column], errors="coerce")
        if strategy == "quantile":
            dataframe[output] = pd.qcut(numeric, q=bins, duplicates="drop").astype(str)
        else:
            dataframe[output] = pd.cut(numeric, bins=bins).astype(str)
        return self._save(dataframe, label=f"Binned {column}", source="monty.bin_numeric")


class VisualizationsCollection(ToolCollection):
    """Create and emit Plotly charts from dataset handles."""

    name = "visualizations"
    description = (
        "Create interactive Plotly chart handles from dataset handle strings and emit chart "
        "handles in chat."
    )

    def __init__(self, context: MontyRuntimeContext) -> None:
        self.context = context

    def tools(self) -> list[ToolSpec]:
        specs = super().tools()
        return [self._with_visualization_help(spec) for spec in specs]

    def _with_visualization_help(self, spec: ToolSpec) -> ToolSpec:
        allowed_kwargs = PLOTLY_KWARGS_BY_TOOL.get(spec.name)
        if allowed_kwargs is None:
            return spec
        arguments = tuple(
            self._with_argument_help(argument, allowed_kwargs) for argument in spec.arguments
        )
        return ToolSpec(
            name=spec.name,
            func=spec.func,
            description=spec.description,
            detailed_description=spec.detailed_description,
            usage_example=spec.usage_example,
            collection=spec.collection,
            collection_description=spec.collection_description,
            arguments=arguments,
            return_annotation=spec.return_annotation,
            return_description=spec.return_description,
        )

    def _with_argument_help(
        self,
        argument: ToolArgument,
        allowed_kwargs: tuple[str, ...],
    ) -> ToolArgument:
        description = argument.description
        if argument.name == "plotly_kwargs":
            valid_keys = ", ".join(allowed_kwargs)
            description = f"{description} Valid plotly_kwargs keys for this helper: {valid_keys}."
        elif argument.name == "extra_plotly_kwargs":
            valid_keys = ", ".join(allowed_kwargs)
            description = f"{description} Valid direct Plotly Express option keys: {valid_keys}."
        elif argument.name == "layout_kwargs":
            description = f"{description} {LAYOUT_KWARGS_HELP}"
        return ToolArgument(
            name=argument.name,
            annotation=argument.annotation,
            default=argument.default,
            kind=argument.kind,
            description=description,
        )

    def _load(self, dataset_handle: str) -> pd.DataFrame:
        handle = _dataset_handle(dataset_handle)
        return self.context.store.load_dataset(self.context.state, handle).to_dataframe()

    def _save_figure(
        self,
        figure: Any,
        *,
        label: str,
        source: str,
        layout_kwargs: dict[str, Any] | None = None,
    ) -> str:
        layout_updates = {
            "colorway": PLOTLY_COLORWAY,
            "margin": {"l": 56, "r": 24, "t": 56 if label else 32, "b": 52},
            "hovermode": "closest",
        }
        if layout_kwargs:
            layout_updates.update(layout_kwargs)
        figure.update_layout(**layout_updates)
        figure_json = json.loads(pio.to_json(figure, validate=True))
        return self.context.store.save_plotly_chart(
            self.context.state,
            figure=figure_json,
            label=label,
            source=source,
        ).handle

    def _plotly_kwargs(
        self,
        plotly_func: Callable[..., Any],
        plotly_kwargs: dict[str, Any] | None,
        *,
        protected_keys: set[str],
        defaults: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        extras = dict(plotly_kwargs or {})
        conflicts = sorted(set(extras) & protected_keys)
        if conflicts:
            raise ValueError(
                "Use the named helper arguments for these options instead of "
                f"plotly_kwargs: {', '.join(conflicts)}"
            )
        allowed_keys = _allowed_plotly_kwargs(plotly_func, protected_keys)
        unsupported = sorted(set(extras) - set(allowed_keys))
        if unsupported:
            raise ValueError(
                f"Unsupported Plotly Express option(s) for {plotly_func.__name__}: "
                + ", ".join(unsupported)
                + f". Valid plotly_kwargs keys: {', '.join(allowed_keys)}"
            )
        return {**(defaults or {}), **extras}

    @tool
    def create_bar_chart(
        self,
        dataset_handle: str,
        x: str,
        y: str,
        *,
        color: str | None = None,
        title: str = "",
        plotly_kwargs: dict[str, Any] | None = None,
        layout_kwargs: dict[str, Any] | None = None,
        **extra_plotly_kwargs: Any,
    ) -> str:
        """Create a Plotly bar chart from a dataset handle.

        Args:
            dataset_handle: Input dataset handle.
            x: X-axis column.
            y: Y-axis column.
            color: Optional color grouping column.
            title: Optional chart title.
            plotly_kwargs: Optional extra keyword arguments passed to plotly.express.bar.
                Use this for less common options such as labels, barmode,
                opacity, text_auto, height, or width. Named helper arguments
                such as x, y, color, and title cannot be overridden here.
            layout_kwargs: Optional layout updates passed to Figure.update_layout
                after the chart is created. Use this for custom axis titles,
                legend placement, margins, hovermode, or template.
            extra_plotly_kwargs: Optional direct Plotly Express options such as
                barmode or text_auto. These are equivalent to putting the same
                keys in plotly_kwargs.

        Returns:
            str: New Plotly chart handle.

        Examples:
            ```python
            counts = value_counts("ds_1", "status")
            chart = create_bar_chart(
                counts,
                "status",
                "count",
                title="Claims by status",
                plotly_kwargs={"text_auto": True},
                layout_kwargs={"xaxis_title": "Status", "yaxis_title": "Claims"},
            )
            emitted = emit_plotly_chart(chart)
            print(chart)
            print(emitted["component"])
            # Prints
            # fig_1
            # a2ui.PlotlyChart
            ```
        """
        kwargs = self._plotly_kwargs(
            px.bar,
            _merge_plotly_kwargs(plotly_kwargs, extra_plotly_kwargs),
            protected_keys=BAR_PROTECTED_KEYS,
            defaults={
                "color_discrete_sequence": PLOTLY_COLORWAY,
                "template": "plotly_white",
            },
        )
        figure = px.bar(
            self._load(dataset_handle),
            x=x,
            y=y,
            color=color,
            title=title,
            **kwargs,
        )
        return self._save_figure(
            figure,
            label=title or "Bar chart",
            source=_dataset_handle(dataset_handle),
            layout_kwargs=layout_kwargs,
        )

    @tool
    def create_line_chart(
        self,
        dataset_handle: str,
        x: str,
        y: str,
        *,
        color: str | None = None,
        title: str = "",
        plotly_kwargs: dict[str, Any] | None = None,
        layout_kwargs: dict[str, Any] | None = None,
        **extra_plotly_kwargs: Any,
    ) -> str:
        """Create a Plotly line chart from a dataset handle.

        Args:
            dataset_handle: Input dataset handle.
            x: X-axis column.
            y: Y-axis column.
            color: Optional color grouping column.
            title: Optional chart title.
            plotly_kwargs: Optional extra keyword arguments passed to plotly.express.line.
                Use this for less common options such as markers, line_shape,
                labels, category_orders, height, or width. Named helper arguments
                such as x, y, color, and title cannot be overridden here.
            layout_kwargs: Optional layout updates passed to Figure.update_layout
                after the chart is created.
            extra_plotly_kwargs: Optional direct Plotly Express options such as
                markers or line_shape. These are equivalent to putting the same
                keys in plotly_kwargs.

        Returns:
            str: New Plotly chart handle.

        Examples:
            ```python
            daily = group_by("ds_1", "inspection_date", {"amount": "sum"})
            chart = create_line_chart(
                daily,
                "inspection_date",
                "amount",
                title="Claim amount over time",
                plotly_kwargs={"markers": True},
            )
            emitted = emit_plotly_chart(chart)
            print(emitted["chart_handle"])
            # Prints
            # fig_1
            ```
        """
        kwargs = self._plotly_kwargs(
            px.line,
            _merge_plotly_kwargs(plotly_kwargs, extra_plotly_kwargs),
            protected_keys=LINE_PROTECTED_KEYS,
            defaults={
                "color_discrete_sequence": PLOTLY_COLORWAY,
                "template": "plotly_white",
            },
        )
        figure = px.line(
            self._load(dataset_handle),
            x=x,
            y=y,
            color=color,
            title=title,
            **kwargs,
        )
        return self._save_figure(
            figure,
            label=title or "Line chart",
            source=_dataset_handle(dataset_handle),
            layout_kwargs=layout_kwargs,
        )

    @tool
    def create_scatter_plot(
        self,
        dataset_handle: str,
        x: str,
        y: str,
        *,
        color: str | None = None,
        title: str = "",
        plotly_kwargs: dict[str, Any] | None = None,
        layout_kwargs: dict[str, Any] | None = None,
        **extra_plotly_kwargs: Any,
    ) -> str:
        """Create a Plotly scatter plot from a dataset handle.

        Args:
            dataset_handle: Input dataset handle.
            x: X-axis column.
            y: Y-axis column.
            color: Optional color grouping column.
            title: Optional chart title.
            plotly_kwargs: Optional extra keyword arguments passed to plotly.express.scatter.
                Use this for less common options such as size, symbol,
                trendline, labels, opacity, height, or width. Named helper
                arguments such as x, y, color, and title cannot be overridden here.
            layout_kwargs: Optional layout updates passed to Figure.update_layout
                after the chart is created.
            extra_plotly_kwargs: Optional direct Plotly Express options such as
                text, size, symbol, or trendline. These are equivalent to putting
                the same keys in plotly_kwargs.

        Returns:
            str: New Plotly chart handle.

        Examples:
            ```python
            chart = create_scatter_plot(
                "ds_1",
                "estimated_amount",
                "approved_amount",
                color="status",
                title="Estimated vs approved amount",
                plotly_kwargs={"opacity": 0.75},
            )
            emitted = emit_plotly_chart(chart)
            print(emitted["component"])
            # Prints
            # a2ui.PlotlyChart
            ```
        """
        kwargs = self._plotly_kwargs(
            px.scatter,
            _merge_plotly_kwargs(plotly_kwargs, extra_plotly_kwargs),
            protected_keys=SCATTER_PROTECTED_KEYS,
            defaults={
                "color_discrete_sequence": PLOTLY_COLORWAY,
                "color_continuous_scale": PLOTLY_CONTINUOUS_SCALE,
                "template": "plotly_white",
            },
        )
        figure = px.scatter(
            self._load(dataset_handle),
            x=x,
            y=y,
            color=color,
            title=title,
            **kwargs,
        )
        return self._save_figure(
            figure,
            label=title or "Scatter plot",
            source=_dataset_handle(dataset_handle),
            layout_kwargs=layout_kwargs,
        )

    @tool
    def create_histogram(
        self,
        dataset_handle: str,
        column: str,
        *,
        color: str | None = None,
        title: str = "",
        nbins: int | None = None,
        plotly_kwargs: dict[str, Any] | None = None,
        layout_kwargs: dict[str, Any] | None = None,
        **extra_plotly_kwargs: Any,
    ) -> str:
        """Create a Plotly histogram from a dataset column.

        Args:
            dataset_handle: Input dataset handle.
            column: Column to plot on the x axis.
            color: Optional color grouping column.
            title: Optional chart title.
            nbins: Optional number of bins.
            plotly_kwargs: Optional extra keyword arguments passed to plotly.express.histogram.
                Use this for less common options such as histnorm, histfunc,
                barmode, marginal, labels, opacity, height, or width. Named
                helper arguments such as column, color, title, and nbins cannot
                be overridden here.
            layout_kwargs: Optional layout updates passed to Figure.update_layout
                after the chart is created.
            extra_plotly_kwargs: Optional direct Plotly Express options such as
                histnorm, histfunc, barmode, or marginal. These are equivalent
                to putting the same keys in plotly_kwargs.

        Returns:
            str: New Plotly chart handle.

        Examples:
            ```python
            chart = create_histogram(
                "ds_1",
                "amount",
                color="status",
                title="Claim amount distribution",
                nbins=20,
                plotly_kwargs={"barmode": "overlay", "opacity": 0.7},
            )
            emitted = emit_plotly_chart(chart)
            print(chart)
            # Prints
            # fig_1
            ```
        """
        kwargs = self._plotly_kwargs(
            px.histogram,
            _merge_plotly_kwargs(plotly_kwargs, extra_plotly_kwargs),
            protected_keys=HISTOGRAM_PROTECTED_KEYS,
            defaults={
                "color_discrete_sequence": PLOTLY_COLORWAY,
                "template": "plotly_white",
            },
        )
        figure = px.histogram(
            self._load(dataset_handle),
            x=column,
            color=color,
            title=title,
            nbins=nbins,
            **kwargs,
        )
        return self._save_figure(
            figure,
            label=title or "Histogram",
            source=_dataset_handle(dataset_handle),
            layout_kwargs=layout_kwargs,
        )

    @tool
    def create_box_plot(
        self,
        dataset_handle: str,
        x: str,
        y: str,
        *,
        color: str | None = None,
        title: str = "",
        plotly_kwargs: dict[str, Any] | None = None,
        layout_kwargs: dict[str, Any] | None = None,
        **extra_plotly_kwargs: Any,
    ) -> str:
        """Create a Plotly box plot from a dataset handle.

        Args:
            dataset_handle: Input dataset handle.
            x: Category column.
            y: Numeric value column.
            color: Optional color grouping column.
            title: Optional chart title.
            plotly_kwargs: Optional extra keyword arguments passed to plotly.express.box.
                Use this for less common options such as points, boxmode,
                notched, labels, height, or width. Named helper arguments such
                as x, y, color, and title cannot be overridden here.
            layout_kwargs: Optional layout updates passed to Figure.update_layout
                after the chart is created.
            extra_plotly_kwargs: Optional direct Plotly Express options such as
                points, boxmode, or notched. These are equivalent to putting the
                same keys in plotly_kwargs.

        Returns:
            str: New Plotly chart handle.

        Examples:
            ```python
            chart = create_box_plot(
                "ds_1",
                "region",
                "amount",
                color="status",
                title="Claim amount by region",
                plotly_kwargs={"points": "outliers"},
            )
            emitted = emit_plotly_chart(chart)
            print(emitted["caption"])
            # Prints
            # Claim amount by region
            ```
        """
        kwargs = self._plotly_kwargs(
            px.box,
            _merge_plotly_kwargs(plotly_kwargs, extra_plotly_kwargs),
            protected_keys=BOX_PROTECTED_KEYS,
            defaults={
                "color_discrete_sequence": PLOTLY_COLORWAY,
                "template": "plotly_white",
            },
        )
        figure = px.box(
            self._load(dataset_handle),
            x=x,
            y=y,
            color=color,
            title=title,
            **kwargs,
        )
        return self._save_figure(
            figure,
            label=title or "Box plot",
            source=_dataset_handle(dataset_handle),
            layout_kwargs=layout_kwargs,
        )

    @tool
    def create_pie_chart(
        self,
        dataset_handle: str,
        names: str,
        values: str,
        *,
        title: str = "",
        plotly_kwargs: dict[str, Any] | None = None,
        layout_kwargs: dict[str, Any] | None = None,
        **extra_plotly_kwargs: Any,
    ) -> str:
        """Create a Plotly pie chart from a dataset handle.

        Args:
            dataset_handle: Input dataset handle.
            names: Category/name column.
            values: Numeric value column.
            title: Optional chart title.
            plotly_kwargs: Optional extra keyword arguments passed to plotly.express.pie.
                Use this for less common options such as color, hole, labels,
                opacity, height, or width. Named helper arguments such as names,
                values, and title cannot be overridden here.
            layout_kwargs: Optional layout updates passed to Figure.update_layout
                after the chart is created.
            extra_plotly_kwargs: Optional direct Plotly Express options such as
                color, hole, or labels. These are equivalent to putting the same
                keys in plotly_kwargs.

        Returns:
            str: New Plotly chart handle.

        Examples:
            ```python
            counts = value_counts("ds_1", "status")
            chart = create_pie_chart(
                counts,
                names="status",
                values="count",
                title="Claim status share",
                plotly_kwargs={"hole": 0.35},
            )
            emitted = emit_plotly_chart(chart)
            print(emitted["component"])
            # Prints
            # a2ui.PlotlyChart
            ```
        """
        kwargs = self._plotly_kwargs(
            px.pie,
            _merge_plotly_kwargs(plotly_kwargs, extra_plotly_kwargs),
            protected_keys=PIE_PROTECTED_KEYS,
            defaults={
                "color_discrete_sequence": PLOTLY_COLORWAY,
                "template": "plotly_white",
            },
        )
        figure = px.pie(
            self._load(dataset_handle),
            names=names,
            values=values,
            title=title,
            **kwargs,
        )
        return self._save_figure(
            figure,
            label=title or "Pie chart",
            source=_dataset_handle(dataset_handle),
            layout_kwargs=layout_kwargs,
        )

    @tool
    def emit_plotly_chart(
        self,
        chart_handle: str,
        *,
        caption: str = "",
    ) -> dict[str, Any]:
        """Render a Plotly chart handle in the chat UI.

        Args:
            chart_handle: Handle pointing to a stored Plotly chart artifact.
            caption: Optional caption shown above the chart.

        Returns:
            dict[str, Any]: Emitted chart metadata.

        Examples:
            ```python
            chart = create_bar_chart("ds_2", "status", "count", title="Claims by status")
            emitted = emit_plotly_chart(chart, caption="Claims by status")
            print(emitted)
            # Prints a dictionary similar to:
            # {
            #     "component": "a2ui.PlotlyChart",
            #     "chart_handle": "fig_1",
            #     "caption": "Claims by status",
            # }
            ```
        """
        chart_handle = _chart_handle(chart_handle)
        chart = self.context.store.load_plotly_chart(self.context.state, chart_handle)
        self.context.state.components.append(
            generate_plotly_chart(
                figure=chart.figure,
                caption=caption or chart.label,
                source_handle=chart_handle,
            )
        )
        return {
            "component": "a2ui.PlotlyChart",
            "chart_handle": chart_handle,
            "caption": caption or chart.label,
        }


class RLMCollection(ToolCollection):
    """Prepare text rows and query sub-LLMs for semantic analysis."""

    name = "rlm"
    description = (
        "Create text lists from dataset handles and query sub-LLMs for row-level or "
        "chunk-level semantic analysis. Async helpers must be called with await, "
        "and all sub-LLM calls share the configured call budget for this artifact session."
    )

    def __init__(self, context: MontyRuntimeContext) -> None:
        self.context = context

    def _load(self, dataset_handle: str) -> pd.DataFrame:
        handle = _dataset_handle(dataset_handle)
        return self.context.store.load_dataset(self.context.state, handle).to_dataframe()

    @property
    def _model_name(self) -> str:
        configured = getattr(self.context.settings, "monty_rlm_model", None)
        return str(configured or self.context.settings.chat_model)

    @property
    def _max_batch_size(self) -> int:
        return int(
            getattr(self.context.settings, "monty_rlm_max_batch_size", DEFAULT_RLM_BATCH_SIZE)
        )

    @property
    def _max_prompt_chars(self) -> int:
        return int(
            getattr(self.context.settings, "monty_rlm_max_prompt_chars", DEFAULT_RLM_PROMPT_CHARS)
        )

    @property
    def _max_llm_calls(self) -> int:
        return int(
            getattr(self.context.settings, "monty_rlm_max_llm_calls", DEFAULT_RLM_MAX_LLM_CALLS)
        )

    def _build_agent(self) -> Agent[None, str]:
        model = (
            TestModel(custom_output_text="RLM test response")
            if self._model_name == "test"
            else self._model_name
        )
        return Agent(
            model,
            output_type=str,
            instructions=(
                "You are a focused sub-LLM for semantic analysis of text snippets. "
                "Answer the caller's prompt directly and concisely. If the prompt asks "
                "for extraction, preserve relevant evidence and avoid inventing facts."
            ),
        )

    async def _query_async(self, agent: Agent[None, str], prompt: str) -> str:
        result = await agent.run(prompt)
        self.context.rlm_usage.incr(result.usage())
        return result.output

    @tool
    def dataset_texts(
        self,
        dataset_handle: str,
        column: str,
        *,
        max_rows: int = 1000,
        skip_empty: bool = True,
    ) -> list[str]:
        """Convert one dataset column into one text string per row.

        Use this before llm_query_batched() when a SQL result or transformed
        dataset contains many rows of notes, descriptions, claim text, or other
        free-form fields. Store the returned list in a REPL variable, then build
        prompts from it without printing the whole list. For multiple text
        columns, call this helper once per column and assign each list its own
        variable name.

        Args:
            dataset_handle: Input dataset handle.
            column: Single column name to convert.
            max_rows: Maximum number of rows to convert.
            skip_empty: Whether to omit rows where the selected value is empty.

        Returns:
            list[str]: One text string per included dataset row for the selected column.

        Examples:
            ```python
            notes = dataset_texts("ds_1", "adjuster_note", max_rows=100)
            print(len(notes))
            print(notes[0])
            # Prints
            # 100
            # Roof shingles show wind damage near the ridge.
            ```
        """
        if max_rows < 1:
            raise ValueError("max_rows must be at least 1.")
        if not isinstance(column, str) or not column:
            raise ValueError("dataset_texts requires exactly one column name.")
        dataframe = self._load(dataset_handle)
        if column not in dataframe.columns:
            raise ValueError(f"Unknown dataset column: {column}")

        texts: list[str] = []
        for value in dataframe[column].head(max_rows):
            text = "" if value is None else str(value).strip()
            if text or not skip_empty:
                texts.append(text)
        return texts

    @tool
    async def llm_query(self, prompt: str) -> str:
        """Query a sub-LLM with one prompt string.

        This is an async helper. In sandbox code, call it with await:
        `answer = await llm_query(prompt)`.

        Args:
            prompt: Prompt to send to the sub-LLM.

        Returns:
            str: The sub-LLM response text.

        Examples:
            ```python
            answer = await llm_query(
                "Classify this note as roof, window, or interior: "
                + "Roof shingles show wind damage near the ridge."
            )
            print(answer)
            # Prints
            # roof
            ```
        """
        prompt = prompt.strip()
        if not prompt:
            raise ValueError("prompt cannot be empty.")
        if len(prompt) > self._max_prompt_chars:
            raise ValueError(
                f"prompt is too long: {len(prompt)} characters > {self._max_prompt_chars}"
            )
        self.context.reserve_rlm_calls(1, max_calls=self._max_llm_calls)
        return await self._query_async(self._build_agent(), prompt)

    @tool
    async def llm_query_batched(self, prompts: list[str]) -> list[str]:
        """Query a sub-LLM for multiple prompt strings concurrently.

        Use this when rows or chunks can be analyzed independently. This helper
        preserves result order. In sandbox code, call it with await:
        `answers = await llm_query_batched(prompts)`.

        Args:
            prompts: Prompt strings to send concurrently.

        Returns:
            list[str]: Sub-LLM response text for each prompt, in input order.

        Examples:
            ```python
            notes = dataset_texts("ds_1", "adjuster_note", max_rows=3)
            prompts = [
                "Classify this note as roof, window, or interior: " + note
                for note in notes
            ]
            answers = await llm_query_batched(prompts)
            print(len(answers))
            print(answers[0])
            # Prints
            # 3
            # roof
            ```
        """
        if not prompts:
            return []
        if len(prompts) > self._max_batch_size:
            raise ValueError(
                f"Too many prompts for one batch: {len(prompts)} > {self._max_batch_size}. "
                "Split the work into smaller batches."
            )
        normalized: list[str] = []
        for index, prompt in enumerate(prompts):
            text = str(prompt).strip()
            if not text:
                raise ValueError(f"Prompt at index {index} is empty.")
            if len(text) > self._max_prompt_chars:
                raise ValueError(
                    f"Prompt at index {index} is too long: "
                    f"{len(text)} characters > {self._max_prompt_chars}"
                )
            normalized.append(text)

        self.context.reserve_rlm_calls(len(normalized), max_calls=self._max_llm_calls)
        agent = self._build_agent()
        results = await asyncio.gather(
            *(self._query_async(agent, prompt) for prompt in normalized),
            return_exceptions=True,
        )
        output: list[str] = []
        for result in results:
            if isinstance(result, BaseException):
                output.append(f"[ERROR] {result}")
            else:
                output.append(result)
        return output


def build_monty_registry(context: MontyRuntimeContext) -> FunctionRegistry:
    registry = FunctionRegistry()
    registry.register_collection(HandlesCollection(context))
    registry.register_collection(DataframeOperationsCollection(context))
    registry.register_collection(RLMCollection(context))
    registry.register_collection(VisualizationsCollection(context))
    return registry
