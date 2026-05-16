"""TFR-specific Monty helper collections."""

from __future__ import annotations

import inspect
import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

import pandas as pd
import plotly.express as px
import plotly.io as pio

from app.core.config import Settings
from app.models.chat_state import TFRChatState
from app.presenters.a2ui import generate_data_table, generate_plotly_chart
from app.services.chat_artifacts import ChatArtifactStore, dataframe_preview

from .registry import FunctionRegistry, ToolArgument, ToolCollection, ToolSpec, tool

FilterOperator = Literal["==", "!=", ">", ">=", "<", "<=", "contains", "in", "isna", "notna"]
PLOTLY_COLORWAY = px.colors.sequential.Viridis
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


@dataclass(slots=True)
class MontyRuntimeContext:
    state: TFRChatState
    settings: Settings

    @property
    def store(self) -> ChatArtifactStore:
        return ChatArtifactStore(self.settings)


class HandlesCollection(ToolCollection):
    """Discover and emit file-backed chat handles."""

    name = "handles"
    description = "Inspect dataset/chart handles and emit handled artifacts into the chat UI."

    def __init__(self, context: MontyRuntimeContext) -> None:
        self.context = context

    @tool
    def list_handles(self) -> list[dict[str, Any]]:
        """List dataset and chart handles available in this chat session.

        Returns:
            list[dict[str, Any]]: Handle metadata including kind, label, row count,
            column count, and source where available.
        """
        return [handle.model_dump() for handle in self.context.state.handles]

    @tool
    def inspect_handle(self, handle: str) -> dict[str, Any]:
        """Inspect one stored dataset or chart handle.

        Args:
            handle: The dataset or chart handle to inspect.

        Returns:
            dict[str, Any]: Metadata for the requested handle.
        """
        return self.context.store.inspect_handle(self.context.state, handle)

    @tool
    def get_dataset(self, dataset_handle: str, *, limit: int = 10) -> dict[str, Any]:
        """Preview rows and columns for a dataset handle.

        Args:
            dataset_handle: Handle pointing to a stored dataset artifact.
            limit: Maximum preview row count.

        Returns:
            dict[str, Any]: Dataset columns, row count, and preview records.
        """
        dataset = self.context.store.load_dataset(self.context.state, dataset_handle)
        return dataframe_preview(dataset, limit=limit)

    @tool
    def put_dataset(
        self,
        rows: list[dict[str, Any]],
        *,
        label: str = "",
    ) -> str:
        """Persist row dictionaries as a new dataset handle.

        Args:
            rows: Row records to persist. Keys become dataset columns.
            label: Optional human-readable label.

        Returns:
            str: New dataset handle.
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
        """
        dataset = self.context.store.load_dataset(self.context.state, dataset_handle)
        rows = dataset.rows[:max_rows]
        self.context.state.components.append(
            generate_data_table(
                headers=dataset.columns,
                rows=rows,
                caption=caption or dataset.label or f"Dataset {dataset_handle}",
                sortable=True,
            )
        )
        return {
            "component": "a2ui.DataTable",
            "dataset_handle": dataset_handle,
            "rendered_rows": len(rows),
            "row_count": dataset.row_count,
        }


class DataframeOperationsCollection(ToolCollection):
    """Create new dataset handles through common dataframe transforms."""

    name = "dataframe_operations"
    description = "Transform stored datasets for EDA and visualization prep."

    def __init__(self, context: MontyRuntimeContext) -> None:
        self.context = context

    def _load(self, dataset_handle: str) -> pd.DataFrame:
        return self.context.store.load_dataset(self.context.state, dataset_handle).to_dataframe()

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
    description = "Create interactive Plotly chart handles and emit them in chat."

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
        return self.context.store.load_dataset(self.context.state, dataset_handle).to_dataframe()

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

        Returns:
            str: New Plotly chart handle.
        """
        kwargs = self._plotly_kwargs(
            px.bar,
            plotly_kwargs,
            protected_keys=BAR_PROTECTED_KEYS,
            defaults={
                "color_discrete_sequence": PLOTLY_COLORWAY,
                "color_continuous_scale": "Viridis",
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
            source=dataset_handle,
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

        Returns:
            str: New Plotly chart handle.
        """
        kwargs = self._plotly_kwargs(
            px.line,
            plotly_kwargs,
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
            source=dataset_handle,
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

        Returns:
            str: New Plotly chart handle.
        """
        kwargs = self._plotly_kwargs(
            px.scatter,
            plotly_kwargs,
            protected_keys=SCATTER_PROTECTED_KEYS,
            defaults={
                "color_discrete_sequence": PLOTLY_COLORWAY,
                "color_continuous_scale": "Viridis",
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
            source=dataset_handle,
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

        Returns:
            str: New Plotly chart handle.
        """
        kwargs = self._plotly_kwargs(
            px.histogram,
            plotly_kwargs,
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
            source=dataset_handle,
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

        Returns:
            str: New Plotly chart handle.
        """
        kwargs = self._plotly_kwargs(
            px.box,
            plotly_kwargs,
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
            source=dataset_handle,
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

        Returns:
            str: New Plotly chart handle.
        """
        kwargs = self._plotly_kwargs(
            px.pie,
            plotly_kwargs,
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
            source=dataset_handle,
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
        """
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


def build_monty_registry(context: MontyRuntimeContext) -> FunctionRegistry:
    registry = FunctionRegistry()
    registry.register_collection(HandlesCollection(context))
    registry.register_collection(DataframeOperationsCollection(context))
    registry.register_collection(VisualizationsCollection(context))
    return registry
