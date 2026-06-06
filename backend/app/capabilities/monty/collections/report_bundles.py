"""Report bundle tools for Monty."""

from __future__ import annotations

from typing import Any

from app.capabilities.monty.collections.base import (
    MontyRuntimeContext,
    _chart_handle,
    _dataset_handle,
)
from app.capabilities.monty.registry import ToolCollection, tool
from app.presenters.a2ui import generate_artifact_bundle_card
from app.services.output_bundles import OutputBundleService


class ReportBundlesCollection(ToolCollection):
    """Create polished HTML report bundles with an accompanying data workbook."""

    name = "report_bundles"
    description = (
        "Build long-form, browser/print-friendly HTML report bundles from dataset and chart "
        "handles. Use this for reports, findings memos, audit summaries, and evidence-heavy "
        "analysis packets. Rendered bundles also save a data workbook."
    )

    def __init__(self, context: MontyRuntimeContext) -> None:
        self.context = context

    @property
    def _service(self) -> OutputBundleService:
        return OutputBundleService(self.context.settings)

    @tool
    def create_report_bundle(
        self,
        title: str,
        subtitle: str = "",
        audience: str = "audit",
        theme: str = "liberty_professional",
    ) -> str:
        """Create a draft HTML report bundle.

        Args:
            title: Report title.
            subtitle: Optional subtitle shown under the title.
            audience: Intended audience label, such as audit or executive.
            theme: Output theme. Only liberty_professional is supported in v1.

        Returns:
            str: New report bundle handle.

        Examples:
            ```python
            report = create_report_bundle(
                "Audit Exception Summary",
                subtitle="Financial claim review results",
            )
            print(report)
            # Prints
            # rpt_1
            ```
        """
        return self._service.create_report_bundle(
            self.context.state,
            title=title,
            subtitle=subtitle,
            audience=audience,
            theme=theme,
        )

    @tool
    def add_report_kpis(
        self,
        report_handle: str,
        metrics: list[dict[str, Any]],
        title: str = "",
    ) -> str:
        """Add a KPI grid section to a report bundle.

        Args:
            report_handle: Report bundle handle such as rpt_1.
            metrics: List of dictionaries with label, value, and optional detail.
            title: Optional section title.

        Returns:
            str: The report bundle handle.

        Examples:
            ```python
            report = create_report_bundle("Audit Snapshot")
            add_report_kpis(report, [{"label": "Reviews", "value": 128}])
            print(report)
            # Prints
            # rpt_1
            ```
        """
        return self._service.add_report_block(
            self.context.state,
            report_handle,
            {"type": "kpis", "metrics": metrics, "title": title},
        )

    @tool
    def add_report_markdown_section(
        self,
        report_handle: str,
        title: str,
        markdown: str,
    ) -> str:
        """Add a narrative Markdown section to a report bundle.

        Args:
            report_handle: Report bundle handle such as rpt_1.
            title: Section title.
            markdown: Markdown body text. Raw HTML is escaped.

        Returns:
            str: The report bundle handle.

        Examples:
            ```python
            report = create_report_bundle("Audit Findings")
            add_report_markdown_section(report, "Key Findings", "- Exceptions cluster by region.")
            print(report)
            # Prints
            # rpt_1
            ```
        """
        return self._service.add_report_block(
            self.context.state,
            report_handle,
            {"type": "markdown", "title": title, "markdown": markdown},
        )

    @tool
    def add_report_chart(
        self,
        report_handle: str,
        chart_handle: str,
        title: str = "",
        caption: str = "",
        width: str = "full",
    ) -> str:
        """Add a Plotly chart section to a report bundle.

        Args:
            report_handle: Report bundle handle such as rpt_1.
            chart_handle: Plotly chart handle such as fig_1.
            title: Optional section title.
            caption: Optional caption below the chart.
            width: Chart width hint. Use full in v1.

        Returns:
            str: The report bundle handle.

        Examples:
            ```python
            report = create_report_bundle("Audit Charts")
            counts = value_counts("ds_1", "status")
            chart = create_bar_chart(counts, "status", "count", title="Claims by status")
            add_report_chart(report, chart, caption="Completed reviews only.")
            print(report)
            # Prints
            # rpt_1
            ```
        """
        chart = _chart_handle(chart_handle)
        self.context.store.load_plotly_chart(self.context.state, chart)
        return self._service.add_report_block(
            self.context.state,
            report_handle,
            {
                "type": "chart",
                "chart_handle": chart,
                "title": title,
                "caption": caption,
                "width": width,
            },
        )

    @tool
    def add_report_table(
        self,
        report_handle: str,
        dataset_handle: str,
        title: str = "",
        caption: str = "",
        columns: list[str] | None = None,
        max_rows: int = 50,
    ) -> str:
        """Add a truncated display table to a report bundle.

        The full dataset is still saved to the bundle workbook.

        Args:
            report_handle: Report bundle handle such as rpt_1.
            dataset_handle: Dataset handle such as ds_1.
            title: Optional section title.
            caption: Optional table caption.
            columns: Optional columns to display in order.
            max_rows: Maximum visual rows to include in the report HTML.

        Returns:
            str: The report bundle handle.

        Examples:
            ```python
            report = create_report_bundle("Top Drivers")
            add_report_table(report, "ds_1", columns=["driver", "count"], max_rows=10)
            print(report)
            # Prints
            # rpt_1
            ```
        """
        dataset = _dataset_handle(dataset_handle)
        self.context.store.load_dataset(self.context.state, dataset)
        if max_rows < 1:
            raise ValueError("max_rows must be at least 1.")
        return self._service.add_report_block(
            self.context.state,
            report_handle,
            {
                "type": "table",
                "dataset_handle": dataset,
                "title": title,
                "caption": caption,
                "columns": columns,
                "max_rows": max_rows,
            },
        )

    @tool
    def render_report_bundle(
        self,
        report_handle: str,
        output_name: str = "",
        include_workbook: bool = True,
    ) -> dict[str, Any]:
        """Render a report bundle to HTML, manifest, spec JSON, and data workbook.

        Args:
            report_handle: Report bundle handle such as rpt_1.
            output_name: Optional output slug. Defaults to title plus timestamp.
            include_workbook: Whether to save data.xlsx for referenced datasets.

        Returns:
            dict[str, Any]: Rendered artifact card payload and file metadata.

        Examples:
            ```python
            report = create_report_bundle("Audit Summary")
            add_report_markdown_section(report, "Summary", "No severe exceptions were found.")
            rendered = render_report_bundle(report)
            print(rendered["handle"])
            # Prints
            # rpt_1
            ```
        """
        return self._service.render_report_bundle(
            self.context.state,
            report_handle,
            output_name=output_name,
            include_workbook=include_workbook,
        )

    @tool
    def emit_report_bundle(self, report_handle: str) -> dict[str, Any]:
        """Render a report bundle card in the chat UI.

        Call render_report_bundle() first if the report has not been rendered.

        Args:
            report_handle: Rendered report bundle handle such as rpt_1.

        Returns:
            dict[str, Any]: Emitted artifact card metadata.

        Examples:
            ```python
            report = create_report_bundle("Audit Summary")
            add_report_markdown_section(report, "Summary", "Ready for review.")
            render_report_bundle(report)
            emitted = emit_report_bundle(report)
            print(emitted["component"])
            # Prints
            # a2ui.ArtifactBundleCard
            ```
        """
        payload = self._service.bundle_payload(self.context.state, report_handle)
        self.context.state.components.append(generate_artifact_bundle_card(**payload))
        return payload
