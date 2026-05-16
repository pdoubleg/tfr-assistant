import pytest
from pydantic_ai import RunContext
from pydantic_ai.models.test import TestModel
from pydantic_ai.usage import RunUsage

from app.agents.chat_agent import build_chat_agent
from app.capabilities.deps import TFRChatDeps
from app.capabilities.monty.runtime import MontyPythonRuntime
from app.core.config import Settings
from app.models.chat_state import TFRChatState
from app.services.chat_artifacts import ChatArtifactStore


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def test_monty_help_lists_registered_collections(tmp_path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        chat_artifacts_dir=tmp_path / "data" / "chat_artifacts",
    )
    runtime = MontyPythonRuntime(TFRChatState(), settings)

    help_text = runtime.help()

    assert "handles" in help_text
    assert "dataframe_operations" in help_text
    assert "visualizations" in help_text
    assert "help('<collection>')" in help_text
    assert "help('<helper>')" in help_text
    assert "math" in help_text
    assert "pandas" in help_text
    assert "not available inside sandbox code" in help_text


def test_monty_help_accepts_multiple_targets(tmp_path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        chat_artifacts_dir=tmp_path / "data" / "chat_artifacts",
    )
    runtime = MontyPythonRuntime(TFRChatState(), settings)

    help_text = runtime.help(["handles", "create_line_chart"])

    assert "Collection: handles" in help_text
    assert "Tool: create_line_chart" in help_text
    assert "Valid plotly_kwargs keys for this helper" in help_text
    assert "\n\n---\n\n" in help_text


def test_monty_visualization_help_lists_valid_plotly_kwargs(tmp_path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        chat_artifacts_dir=tmp_path / "data" / "chat_artifacts",
    )
    runtime = MontyPythonRuntime(TFRChatState(), settings)

    line_help = runtime.help("create_line_chart")
    bar_help = runtime.help("create_bar_chart")

    assert "Valid plotly_kwargs keys for this helper" in line_help
    assert "markers" in line_help
    assert "line_shape" in line_help
    assert "color_continuous_scale" not in line_help
    assert "Any JSON-safe Figure.update_layout key is accepted" in line_help
    assert "color_continuous_scale" in bar_help


@pytest.mark.anyio
async def test_chat_agent_exposes_prefixed_monty_tools_without_execute_conflict(tmp_path) -> None:
    settings = Settings(
        chat_model="test",
        data_dir=tmp_path / "data",
        chat_artifacts_dir=tmp_path / "data" / "chat_artifacts",
    )
    state = TFRChatState()
    agent = build_chat_agent(settings)
    ctx = RunContext(
        deps=TFRChatDeps(state, settings=settings),
        model=TestModel(),
        usage=RunUsage(),
    )

    tool_names: list[str] = []
    for toolset in agent.toolsets:
        tool_names.extend((await toolset.get_tools(ctx)).keys())

    assert "execute" in tool_names
    assert "python_sandbox_execute" in tool_names
    assert "python_sandbox_help" in tool_names


@pytest.mark.anyio
async def test_monty_tool_docstrings_populate_registered_schema(tmp_path) -> None:
    settings = Settings(
        chat_model="test",
        data_dir=tmp_path / "data",
        chat_artifacts_dir=tmp_path / "data" / "chat_artifacts",
    )
    ctx = RunContext(
        deps=TFRChatDeps(TFRChatState(), settings=settings),
        model=TestModel(),
        usage=RunUsage(),
    )

    tools = await build_chat_agent(settings).toolsets[1].get_tools(ctx)

    help_tool = tools["python_sandbox_help"].tool_def
    execute_tool = tools["python_sandbox_execute"].tool_def

    assert "Monty sandbox collections" in help_tool.description
    assert (
        "collection or helper name"
        in help_tool.parameters_json_schema["properties"]["name"]["description"]
    )
    assert "dataframe handles and Plotly charts" in execute_tool.description
    code_description = execute_tool.parameters_json_schema["properties"]["code"]["description"]
    assert "restrictive Monty" in code_description
    assert "dataset or chart handle strings" in code_description


@pytest.mark.anyio
async def test_chat_agent_runs_with_monty_capability_enabled(tmp_path) -> None:
    settings = Settings(
        chat_model="test",
        data_dir=tmp_path / "data",
        chat_artifacts_dir=tmp_path / "data" / "chat_artifacts",
    )
    agent = build_chat_agent(settings)

    result = await agent.run(
        "hello",
        deps=TFRChatDeps(TFRChatState(), settings=settings),
    )

    assert "TFR assistant is connected" in result.output


@pytest.mark.anyio
async def test_monty_execute_runs_udfs_and_emits_plotly_chart(tmp_path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        chat_artifacts_dir=tmp_path / "data" / "chat_artifacts",
    )
    state = TFRChatState()
    store = ChatArtifactStore(settings)
    dataset_handle = store.save_dataset(
        state,
        columns=["category", "amount"],
        rows=[["A", 10], ["A", 15], ["B", 7]],
        label="Example rows",
        source="test",
    ).handle
    runtime = MontyPythonRuntime(state, settings)

    result = await runtime.execute(
        f"""
counts = value_counts({dataset_handle!r}, "category")
chart = create_bar_chart(counts, "category", "count", title="Counts")
emitted = emit_plotly_chart(chart)
print(emitted["component"])
"""
    )

    assert result["status"] == "success"
    assert "a2ui.PlotlyChart" in result["stdout"]
    assert len(result["handles"]) == 2
    assert {handle["kind"] for handle in result["handles"]} == {
        "dataset",
        "plotly_chart",
    }
    assert state.components[-1].type == "a2ui.PlotlyChart"


@pytest.mark.anyio
async def test_visualization_helpers_accept_extra_plotly_and_layout_kwargs(tmp_path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        chat_artifacts_dir=tmp_path / "data" / "chat_artifacts",
    )
    state = TFRChatState()
    store = ChatArtifactStore(settings)
    dataset_handle = store.save_dataset(
        state,
        columns=["category", "amount"],
        rows=[["A", 10], ["A", 15], ["B", 7]],
        label="Example rows",
        source="test",
    ).handle
    runtime = MontyPythonRuntime(state, settings)

    result = await runtime.execute(
        f"""
chart = create_box_plot(
    {dataset_handle!r},
    "category",
    "amount",
    title="Distribution",
    plotly_kwargs={{"points": "all", "labels": {{"amount": "Amount"}}}},
    layout_kwargs={{"showlegend": False}},
)
emit_plotly_chart(chart)
"""
    )

    assert result["status"] == "success"
    assert state.handles[-1].kind == "plotly_chart"
    chart = store.load_plotly_chart(state, state.handles[-1].handle)
    assert chart.figure["layout"]["showlegend"] is False
    assert chart.figure["data"][0]["boxpoints"] == "all"


@pytest.mark.anyio
async def test_visualization_helpers_reject_plotly_kwargs_that_override_named_args(
    tmp_path,
) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        chat_artifacts_dir=tmp_path / "data" / "chat_artifacts",
    )
    state = TFRChatState()
    dataset_handle = (
        ChatArtifactStore(settings)
        .save_dataset(
            state,
            columns=["category", "amount"],
            rows=[["A", 10], ["B", 7]],
        )
        .handle
    )
    runtime = MontyPythonRuntime(state, settings)

    result = await runtime.execute(
        f"""
create_line_chart(
    {dataset_handle!r},
    "category",
    "amount",
    plotly_kwargs={{"x": "amount"}},
)
"""
    )

    assert result["status"] == "error"
    assert "Use the named helper arguments" in result["error"]
    assert "x" in result["error"]


@pytest.mark.anyio
async def test_visualization_helpers_reject_unsupported_plotly_kwargs(tmp_path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        chat_artifacts_dir=tmp_path / "data" / "chat_artifacts",
    )
    state = TFRChatState()
    dataset_handle = (
        ChatArtifactStore(settings)
        .save_dataset(
            state,
            columns=["category", "amount"],
            rows=[["A", 10], ["B", 7]],
        )
        .handle
    )
    runtime = MontyPythonRuntime(state, settings)

    result = await runtime.execute(
        f"""
create_line_chart(
    {dataset_handle!r},
    "category",
    "amount",
    plotly_kwargs={{"color_continuous_scale": "Viridis"}},
)
"""
    )

    assert result["status"] == "error"
    assert (
        "Unsupported Plotly Express option(s) for line: color_continuous_scale" in result["error"]
    )
