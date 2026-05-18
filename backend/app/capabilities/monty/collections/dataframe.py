"""Dataframe transform tools for Monty."""

from __future__ import annotations

from typing import Any, Literal

import pandas as pd

from app.capabilities.monty.collections.base import (
    FilterOperator,
    MontyRuntimeContext,
    _as_column_list,
    _dataset_handle,
    _require_columns,
    _require_output_columns,
)
from app.capabilities.monty.registry import ToolCollection, tool


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
        metric columns, such as items_completed and items_other. The tool
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
