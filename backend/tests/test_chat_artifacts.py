import json

import pytest

from app.core.config import Settings
from app.models.chat_state import TFRChatState
from app.services.chat_artifacts import ArtifactNotFoundError, ChatArtifactStore


def test_artifact_store_writes_and_reads_dataset_json(tmp_path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        chat_artifacts_dir=tmp_path / "data" / "chat_artifacts",
    )
    state = TFRChatState(artifact_session_id="test-session")
    store = ChatArtifactStore(settings)

    artifact = store.save_dataset(
        state,
        columns=["category", "amount"],
        rows=[["A", 10], ["B", 20]],
        label="Example dataset",
        source="test",
    )

    assert artifact.handle == "ds_1"
    artifact_path = (
        tmp_path / "data" / "chat_artifacts" / state.artifact_session_id / f"{artifact.handle}.json"
    )
    assert artifact_path.exists()
    assert json.loads(artifact_path.read_text(encoding="utf-8"))["kind"] == "dataset"

    loaded = store.load_dataset(state, artifact.handle)

    assert loaded.columns == ["category", "amount"]
    assert loaded.rows == [["A", 10], ["B", 20]]
    assert state.handles[0].handle == artifact.handle
    assert state.handles[0].row_count == 2


def test_artifact_store_rejects_unknown_handles(tmp_path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        chat_artifacts_dir=tmp_path / "data" / "chat_artifacts",
    )
    state = TFRChatState(artifact_session_id="test-session")
    store = ChatArtifactStore(settings)

    with pytest.raises(ArtifactNotFoundError, match="Unknown artifact handle"):
        store.load_dataset(state, "dataset_missing")


def test_artifact_store_sanitizes_plotly_figures(tmp_path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        chat_artifacts_dir=tmp_path / "data" / "chat_artifacts",
    )
    state = TFRChatState(artifact_session_id="test-session")
    store = ChatArtifactStore(settings)

    chart = store.save_plotly_chart(
        state,
        figure={
            "data": [{"type": "bar", "x": ["A"], "y": [1]}],
            "layout": {"title": {"text": "Example"}},
            "config": {"unsafe": True},
        },
        label="Example chart",
        source="test",
    )

    assert chart.handle == "fig_1"
    loaded = store.load_plotly_chart(state, chart.handle)

    assert loaded.figure == {
        "data": [{"type": "bar", "x": ["A"], "y": [1]}],
        "layout": {"title": {"text": "Example"}},
    }
    assert state.handles[-1].kind == "plotly_chart"


def test_artifact_store_increments_short_handles_per_kind(tmp_path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        chat_artifacts_dir=tmp_path / "data" / "chat_artifacts",
    )
    state = TFRChatState(artifact_session_id="test-session")
    store = ChatArtifactStore(settings)

    first_dataset = store.save_dataset(state, columns=["value"], rows=[[1]])
    second_dataset = store.save_dataset(state, columns=["value"], rows=[[2]])
    first_chart = store.save_plotly_chart(state, figure={"data": [], "layout": {}})

    assert first_dataset.handle == "ds_1"
    assert second_dataset.handle == "ds_2"
    assert first_chart.handle == "fig_1"
