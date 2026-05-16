"""Presenter helpers for converting backend data into chat-rendered A2UI payloads."""

from typing import Any

from app.models.a2ui import A2UIComponent


def generate_data_table(
    headers: list[str],
    rows: list[list[Any]],
    caption: str = "",
    *,
    sortable: bool = True,
    copyable: bool = True,
    downloadable: bool = True,
) -> A2UIComponent:
    """Build a data-table component payload for the chat pane."""

    return A2UIComponent(
        type="a2ui.DataTable",
        props={
            "headers": headers,
            "rows": rows,
            "caption": caption,
            "sortable": sortable,
            "copyable": copyable,
            "downloadable": downloadable,
        },
        layout={"width": "full"},
        zone="chat",
    )


def generate_code_disclosure(
    *,
    code: str,
    language: str,
    title: str,
    caption: str = "",
    default_open: bool = False,
    copyable: bool = True,
) -> A2UIComponent:
    """Build a reusable collapsible code component payload for the chat pane."""

    return A2UIComponent(
        type="a2ui.CodeDisclosure",
        props={
            "code": code,
            "language": language,
            "title": title,
            "caption": caption,
            "defaultOpen": default_open,
            "copyable": copyable,
        },
        layout={"width": "full"},
        zone="chat",
    )
