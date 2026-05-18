"""Plotly visualization tools for Monty."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import pandas as pd
import plotly.express as px
import plotly.io as pio

from app.capabilities.monty.collections.base import (
    BAR_PROTECTED_KEYS,
    BOX_PROTECTED_KEYS,
    HISTOGRAM_PROTECTED_KEYS,
    LAYOUT_KWARGS_HELP,
    LINE_PROTECTED_KEYS,
    PIE_PROTECTED_KEYS,
    PLOTLY_COLORWAY,
    PLOTLY_CONTINUOUS_SCALE,
    PLOTLY_KWARGS_BY_TOOL,
    SCATTER_PROTECTED_KEYS,
    MontyRuntimeContext,
    _allowed_plotly_kwargs,
    _chart_handle,
    _dataset_handle,
    _merge_plotly_kwargs,
)
from app.capabilities.monty.registry import ToolArgument, ToolCollection, ToolSpec, tool
from app.presenters.a2ui import generate_plotly_chart


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
            description = f"{description} Valid plotly_kwargs keys for this tool: {valid_keys}."
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
                "Use the named tool arguments for these options instead of "
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
                opacity, text_auto, height, or width. Named tool arguments
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
                labels, category_orders, height, or width. Named tool arguments
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
                trendline, labels, opacity, height, or width. Named tool
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
                tool arguments such as column, color, title, and nbins cannot
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
                notched, labels, height, or width. Named tool arguments such
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
                opacity, height, or width. Named tool arguments such as names,
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
