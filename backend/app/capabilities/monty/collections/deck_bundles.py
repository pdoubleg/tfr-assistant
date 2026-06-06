"""Deck bundle tools for Monty."""

from __future__ import annotations

from typing import Any

from app.capabilities.monty.collections.base import (
    MontyRuntimeContext,
    _chart_handle,
    _dataset_handle,
)
from app.capabilities.monty.registry import ToolCollection, tool
from app.presenters.a2ui import generate_artifact_bundle_card
from app.services.output_bundles import OutputBundleService, validate_custom_elements


class DeckBundlesCollection(ToolCollection):
    """Create PowerPoint deck bundles with an accompanying data workbook."""

    name = "deck_bundles"
    description = (
        "Build slide-first PowerPoint .pptx bundles from dataset and chart handles. Use this "
        "for slides, presentations, executive briefings, board decks, and meeting-ready "
        "materials. Rendered bundles also save a data workbook."
    )

    def __init__(self, context: MontyRuntimeContext) -> None:
        self.context = context

    @property
    def _service(self) -> OutputBundleService:
        return OutputBundleService(self.context.settings)

    @tool
    def create_deck_bundle(
        self,
        title: str,
        subtitle: str = "",
        audience: str = "executive",
        theme: str = "liberty_professional",
        layout: str = "wide",
    ) -> str:
        """Create a draft PowerPoint deck bundle.

        Args:
            title: Deck title.
            subtitle: Optional subtitle shown on title slides.
            audience: Intended audience label, such as executive or audit.
            theme: Output theme. Only liberty_professional is supported in v1.
            layout: Slide layout. Only wide is supported in v1.

        Returns:
            str: New deck bundle handle.

        Examples:
            ```python
            deck = create_deck_bundle(
                "Audit Exception Briefing",
                subtitle="Financial claim review results",
            )
            print(deck)
            # Prints
            # deck_1
            ```
        """
        return self._service.create_deck_bundle(
            self.context.state,
            title=title,
            subtitle=subtitle,
            audience=audience,
            theme=theme,
            layout=layout,
        )

    @tool
    def add_title_slide(
        self,
        deck_handle: str,
        title: str = "",
        subtitle: str = "",
        kicker: str = "",
        notes: str = "",
    ) -> str:
        """Add a title slide to a deck bundle.

        Args:
            deck_handle: Deck bundle handle such as deck_1.
            title: Optional slide title. Defaults to the deck title when blank.
            subtitle: Optional slide subtitle.
            kicker: Optional small label above the title.
            notes: Optional speaker notes.

        Returns:
            str: The deck bundle handle.

        Examples:
            ```python
            deck = create_deck_bundle("Audit Briefing")
            add_title_slide(deck, kicker="Targeted file review")
            print(deck)
            # Prints
            # deck_1
            ```
        """
        bundle = self.context.store.load_output_bundle(self.context.state, deck_handle)
        return self._service.add_deck_slide(
            self.context.state,
            deck_handle,
            {
                "type": "title",
                "title": title or bundle.title,
                "subtitle": subtitle or bundle.subtitle,
                "kicker": kicker,
                "notes": notes,
            },
        )

    @tool
    def add_metric_slide(
        self,
        deck_handle: str,
        title: str,
        metrics: list[dict[str, Any]],
        notes: str = "",
    ) -> str:
        """Add a metric summary slide to a deck bundle.

        Args:
            deck_handle: Deck bundle handle such as deck_1.
            title: Slide title.
            metrics: List of dictionaries with label, value, and optional detail.
            notes: Optional speaker notes.

        Returns:
            str: The deck bundle handle.

        Examples:
            ```python
            deck = create_deck_bundle("Audit Briefing")
            add_metric_slide(deck, "Snapshot", [{"label": "Reviews", "value": 128}])
            print(deck)
            # Prints
            # deck_1
            ```
        """
        return self._service.add_deck_slide(
            self.context.state,
            deck_handle,
            {"type": "metrics", "title": title, "metrics": metrics, "notes": notes},
        )

    @tool
    def add_findings_slide(
        self,
        deck_handle: str,
        title: str,
        findings: list[str] | str,
        notes: str = "",
    ) -> str:
        """Add a findings bullet slide to a deck bundle.

        Args:
            deck_handle: Deck bundle handle such as deck_1.
            title: Slide title.
            findings: List of finding strings, or newline-delimited bullets.
            notes: Optional speaker notes.

        Returns:
            str: The deck bundle handle.

        Examples:
            ```python
            deck = create_deck_bundle("Audit Briefing")
            add_findings_slide(deck, "Key Findings", ["Exceptions cluster by form."])
            print(deck)
            # Prints
            # deck_1
            ```
        """
        return self._service.add_deck_slide(
            self.context.state,
            deck_handle,
            {"type": "findings", "title": title, "findings": findings, "notes": notes},
        )

    @tool
    def add_chart_slide(
        self,
        deck_handle: str,
        title: str,
        chart_handle: str,
        caption: str = "",
        notes: str = "",
    ) -> str:
        """Add a chart slide to a deck bundle.

        The Plotly chart is exported as a static image during rendering.

        Args:
            deck_handle: Deck bundle handle such as deck_1.
            title: Slide title.
            chart_handle: Plotly chart handle such as fig_1.
            caption: Optional chart caption.
            notes: Optional speaker notes.

        Returns:
            str: The deck bundle handle.

        Examples:
            ```python
            deck = create_deck_bundle("Audit Briefing")
            counts = value_counts("ds_1", "status")
            chart = create_bar_chart(counts, "status", "count", title="Claims by status")
            add_chart_slide(deck, "Claim Status", chart)
            print(deck)
            # Prints
            # deck_1
            ```
        """
        chart = _chart_handle(chart_handle)
        self.context.store.load_plotly_chart(self.context.state, chart)
        return self._service.add_deck_slide(
            self.context.state,
            deck_handle,
            {
                "type": "chart",
                "title": title,
                "chart_handle": chart,
                "caption": caption,
                "notes": notes,
            },
        )

    @tool
    def add_table_slide(
        self,
        deck_handle: str,
        title: str,
        dataset_handle: str,
        columns: list[str] | None = None,
        max_rows: int = 12,
        notes: str = "",
    ) -> str:
        """Add a truncated table slide to a deck bundle.

        The full dataset is still saved to the bundle workbook.

        Args:
            deck_handle: Deck bundle handle such as deck_1.
            title: Slide title.
            dataset_handle: Dataset handle such as ds_1.
            columns: Optional columns to display in order.
            max_rows: Maximum visual rows to include on the slide.
            notes: Optional speaker notes.

        Returns:
            str: The deck bundle handle.

        Examples:
            ```python
            deck = create_deck_bundle("Audit Briefing")
            add_table_slide(deck, "Top Drivers", "ds_1", max_rows=8)
            print(deck)
            # Prints
            # deck_1
            ```
        """
        dataset = _dataset_handle(dataset_handle)
        self.context.store.load_dataset(self.context.state, dataset)
        if max_rows < 1:
            raise ValueError("max_rows must be at least 1.")
        return self._service.add_deck_slide(
            self.context.state,
            deck_handle,
            {
                "type": "table",
                "title": title,
                "dataset_handle": dataset,
                "columns": columns,
                "max_rows": max_rows,
                "notes": notes,
            },
        )

    @tool
    def add_custom_slide(
        self,
        deck_handle: str,
        title: str,
        elements: list[dict[str, Any]],
        notes: str = "",
    ) -> str:
        """Add a custom slide from vetted layout elements.

        Element kinds must be text, shape, callout, metric, table, or chart. Each
        element must include a box with x, y, w, and h in PowerPoint inches.

        Args:
            deck_handle: Deck bundle handle such as deck_1.
            title: Slide title.
            elements: Vetted slide element dictionaries.
            notes: Optional speaker notes.

        Returns:
            str: The deck bundle handle.

        Examples:
            ```python
            deck = create_deck_bundle("Audit Briefing")
            add_custom_slide(
                deck,
                "Custom",
                [{"kind": "text", "text": "Summary", "box": {"x": 0.7, "y": 1, "w": 4, "h": 0.5}}],
            )
            print(deck)
            # Prints
            # deck_1
            ```
        """
        return self._service.add_deck_slide(
            self.context.state,
            deck_handle,
            {
                "type": "custom",
                "title": title,
                "elements": validate_custom_elements(elements),
                "notes": notes,
            },
        )

    @tool
    def render_deck_bundle(
        self,
        deck_handle: str,
        output_name: str = "",
        include_workbook: bool = True,
    ) -> dict[str, Any]:
        """Render a deck bundle to PPTX, manifest, spec JSON, and data workbook.

        Args:
            deck_handle: Deck bundle handle such as deck_1.
            output_name: Optional output slug. Defaults to title plus timestamp.
            include_workbook: Whether to save data.xlsx for referenced datasets.

        Returns:
            dict[str, Any]: Rendered artifact card payload and file metadata.

        Examples:
            ```python
            deck = create_deck_bundle("Audit Briefing")
            add_title_slide(deck)
            rendered = render_deck_bundle(deck)
            print(rendered["handle"])
            # Prints
            # deck_1
            ```
        """
        return self._service.render_deck_bundle(
            self.context.state,
            deck_handle,
            output_name=output_name,
            include_workbook=include_workbook,
        )

    @tool
    def emit_deck_bundle(self, deck_handle: str) -> dict[str, Any]:
        """Render a deck bundle card in the chat UI.

        Call render_deck_bundle() first if the deck has not been rendered.

        Args:
            deck_handle: Rendered deck bundle handle such as deck_1.

        Returns:
            dict[str, Any]: Emitted artifact card metadata.

        Examples:
            ```python
            deck = create_deck_bundle("Audit Briefing")
            add_title_slide(deck)
            render_deck_bundle(deck)
            emitted = emit_deck_bundle(deck)
            print(emitted["component"])
            # Prints
            # a2ui.ArtifactBundleCard
            ```
        """
        payload = self._service.bundle_payload(self.context.state, deck_handle)
        self.context.state.components.append(generate_artifact_bundle_card(**payload))
        return payload
