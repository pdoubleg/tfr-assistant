"""File-backed chat artifacts shared by SQL and Python repl tools."""

from __future__ import annotations

import json
import math
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

import pandas as pd
from pydantic import BaseModel, Field

from app.core.config import Settings, get_settings
from app.models.chat_state import ChatHandleMetadata, TFRChatState

ArtifactKind = Literal["dataset", "plotly_chart"]

_SAFE_HANDLE_RE = re.compile(r"^[A-Za-z0-9_.-]+$")


class ArtifactNotFoundError(KeyError):
    """Raised when a chat artifact handle cannot be resolved."""


class DatasetArtifact(BaseModel):
    handle: str
    kind: Literal["dataset"] = "dataset"
    columns: list[str]
    rows: list[list[Any]]
    label: str = ""
    source: str = ""
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())

    @property
    def row_count(self) -> int:
        return len(self.rows)

    @property
    def column_count(self) -> int:
        return len(self.columns)

    def to_dataframe(self) -> pd.DataFrame:
        return pd.DataFrame(self.rows, columns=self.columns)


class PlotlyChartArtifact(BaseModel):
    handle: str
    kind: Literal["plotly_chart"] = "plotly_chart"
    figure: dict[str, Any]
    label: str = ""
    source: str = ""
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


class ChatArtifactStore:
    """Persist per-chat datasets and chart specs as local JSON artifacts."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.root = _resolve_path(self.settings.chat_artifacts_dir, self.settings)
        self.root.mkdir(parents=True, exist_ok=True)

    def save_dataset(
        self,
        state: TFRChatState,
        *,
        columns: list[str],
        rows: list[list[Any]],
        label: str = "",
        source: str = "",
    ) -> DatasetArtifact:
        artifact = DatasetArtifact(
            handle=self._new_handle(state, "dataset"),
            columns=[str(column) for column in columns],
            rows=[[_json_safe_value(cell) for cell in row] for row in rows],
            label=label,
            source=source,
        )
        self._write_artifact(state, artifact.handle, artifact.model_dump())
        self._upsert_handle(
            state,
            ChatHandleMetadata(
                handle=artifact.handle,
                kind="dataset",
                label=label,
                row_count=artifact.row_count,
                column_count=artifact.column_count,
                columns=artifact.columns,
                source=source,
                created_at=artifact.created_at,
            ),
        )
        return artifact

    def save_dataframe(
        self,
        state: TFRChatState,
        dataframe: pd.DataFrame,
        *,
        label: str = "",
        source: str = "",
    ) -> DatasetArtifact:
        normalized = dataframe.astype(object).where(pd.notna(dataframe), None)
        rows = normalized.values.tolist()
        return self.save_dataset(
            state,
            columns=[str(column) for column in normalized.columns],
            rows=rows,
            label=label,
            source=source,
        )

    def load_dataset(self, state: TFRChatState, handle: str) -> DatasetArtifact:
        payload = self._read_artifact(state, handle)
        if payload.get("kind") != "dataset":
            raise TypeError(f"Handle {handle!r} is not a dataset artifact.")
        return DatasetArtifact.model_validate(payload)

    def save_plotly_chart(
        self,
        state: TFRChatState,
        *,
        figure: dict[str, Any],
        label: str = "",
        source: str = "",
    ) -> PlotlyChartArtifact:
        artifact = PlotlyChartArtifact(
            handle=self._new_handle(state, "chart"),
            figure=sanitize_plotly_figure(figure),
            label=label,
            source=source,
        )
        self._write_artifact(state, artifact.handle, artifact.model_dump())
        self._upsert_handle(
            state,
            ChatHandleMetadata(
                handle=artifact.handle,
                kind="plotly_chart",
                label=label,
                source=source,
                created_at=artifact.created_at,
            ),
        )
        return artifact

    def load_plotly_chart(self, state: TFRChatState, handle: str) -> PlotlyChartArtifact:
        payload = self._read_artifact(state, handle)
        if payload.get("kind") != "plotly_chart":
            raise TypeError(f"Handle {handle!r} is not a Plotly chart artifact.")
        return PlotlyChartArtifact.model_validate(payload)

    def inspect_handle(self, state: TFRChatState, handle: str) -> dict[str, Any]:
        metadata = next((item for item in state.handles if item.handle == handle), None)
        if metadata is None:
            self._read_artifact(state, handle)
            return {"handle": handle}
        return metadata.model_dump()

    def _session_dir(self, state: TFRChatState) -> Path:
        if not state.artifact_session_id:
            state.artifact_session_id = str(uuid4())
        if not _SAFE_HANDLE_RE.match(state.artifact_session_id):
            raise ValueError("Invalid artifact session id.")
        session_dir = (self.root / state.artifact_session_id).resolve()
        session_dir.relative_to(self.root.resolve())
        session_dir.mkdir(parents=True, exist_ok=True)
        return session_dir

    def _artifact_path(self, state: TFRChatState, handle: str) -> Path:
        if not _SAFE_HANDLE_RE.match(handle):
            raise ValueError(f"Invalid artifact handle: {handle!r}")
        path = (self._session_dir(state) / f"{handle}.json").resolve()
        path.relative_to(self._session_dir(state))
        return path

    def _write_artifact(self, state: TFRChatState, handle: str, payload: dict[str, Any]) -> None:
        self._artifact_path(state, handle).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _read_artifact(self, state: TFRChatState, handle: str) -> dict[str, Any]:
        path = self._artifact_path(state, handle)
        if not path.exists():
            raise ArtifactNotFoundError(f"Unknown artifact handle: {handle}")
        return json.loads(path.read_text(encoding="utf-8"))

    def _new_handle(self, state: TFRChatState, kind: Literal["dataset", "chart"]) -> str:
        prefix = "ds" if kind == "dataset" else "fig"
        pattern = re.compile(rf"^{re.escape(prefix)}_(\d+)$")
        used_indexes: set[int] = set()

        for metadata in state.handles:
            match = pattern.match(metadata.handle)
            if match:
                used_indexes.add(int(match.group(1)))

        session_dir = self._session_dir(state)
        for path in session_dir.glob(f"{prefix}_*.json"):
            match = pattern.match(path.stem)
            if match:
                used_indexes.add(int(match.group(1)))

        next_index = 1
        while next_index in used_indexes:
            next_index += 1
        return f"{prefix}_{next_index}"

    def _upsert_handle(self, state: TFRChatState, metadata: ChatHandleMetadata) -> None:
        state.handles = [item for item in state.handles if item.handle != metadata.handle]
        state.handles.append(metadata)


def dataframe_preview(dataset: DatasetArtifact, limit: int = 10) -> dict[str, Any]:
    return {
        "handle": dataset.handle,
        "columns": dataset.columns,
        "row_count": dataset.row_count,
        "preview_rows": [
            dict(zip(dataset.columns, row, strict=False)) for row in dataset.rows[:limit]
        ],
    }


def sanitize_plotly_figure(figure: dict[str, Any]) -> dict[str, Any]:
    """Return a JSON-safe Plotly figure payload with only renderable figure keys."""

    if not isinstance(figure, dict):
        raise TypeError("Plotly figure must be a dictionary.")

    sanitized: dict[str, Any] = {
        "data": _json_safe_value(figure.get("data", [])),
        "layout": _json_safe_value(figure.get("layout", {})),
    }
    if "frames" in figure:
        sanitized["frames"] = _json_safe_value(figure["frames"])

    if not isinstance(sanitized["data"], list):
        raise ValueError("Plotly figure data must be a list.")
    if not isinstance(sanitized["layout"], dict):
        raise ValueError("Plotly figure layout must be a dictionary.")
    if "frames" in sanitized and not isinstance(sanitized["frames"], list):
        raise ValueError("Plotly figure frames must be a list when provided.")
    return sanitized


def _resolve_path(path: Path, settings: Settings) -> Path:
    if path.is_absolute():
        return path.resolve()
    return (settings.data_dir.parent / path).resolve()


def _json_safe_value(value: Any) -> Any:
    if value is None or isinstance(value, str | int | bool):
        return value
    if isinstance(value, float):
        return None if math.isnan(value) or math.isinf(value) else value
    if isinstance(value, list | tuple):
        return [_json_safe_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_safe_value(item) for key, item in value.items()}
    if hasattr(value, "tolist"):
        return _json_safe_value(value.tolist())
    if hasattr(value, "item"):
        try:
            return _json_safe_value(value.item())
        except ValueError:
            return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)
