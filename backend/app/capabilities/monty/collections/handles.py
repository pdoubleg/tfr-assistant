"""Handle discovery and emission tools for Monty."""

from __future__ import annotations

from typing import Any

import pandas as pd

from app.capabilities.monty.collections.base import (
    MontyRuntimeContext,
    _dataset_handle,
    _format_dataset_description,
    _format_handle_description,
)
from app.capabilities.monty.registry import ToolCollection, tool
from app.presenters.a2ui import generate_data_table
from app.services.chat_artifacts import dataframe_preview


class HandlesCollection(ToolCollection):
    """Discover and emit file-backed chat handles."""

    name = "handles"
    description = (
        "List and describe dataset/chart handles, preview dataset metadata only when code "
        "needs a dict, and emit handled artifacts into the chat UI. Monty tools consume "
        "handle strings; they do not load SQL tables or dataframe objects into variables."
    )

    def __init__(self, context: MontyRuntimeContext) -> None:
        self.context = context

    @tool
    def describe_handles(self) -> str:
        """Return a compact text inventory of available dataset and chart handles.

        Prefer this over list_handles() when the next step is deciding which
        handle string to pass into dataframe or visualization tools. Dataset
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

        This is a low-level structured tool. Prefer describe_handles() when a
        string summary is enough. Pass dataset handle strings such as "ds_1"
        directly to dataframe and chart tools.

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

        This is a low-level structured tool. Prefer describe_handle() when a
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
        dataset_handle string directly to Monty tools.

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

        This is a low-level dict tool for code that must inspect columns,
        row_count, or preview_rows programmatically. Prefer describe_dataset()
        when a string summary is enough. This does not return a dataframe,
        complete dataset, or new handle. Do not build charts or transformed
        datasets from preview_rows because preview_rows may omit most of the
        dataset. For real transforms, pass the original handle string to tools
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
        tools.

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
