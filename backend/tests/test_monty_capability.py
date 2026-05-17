import pytest
from pydantic_ai import RunContext
from pydantic_ai.models.test import TestModel
from pydantic_ai.usage import RunUsage

from app.agents.chat_agent import build_chat_agent
from app.capabilities.deps import TFRChatDeps
from app.capabilities.monty import MontyPythonCapability
from app.capabilities.monty.collections import PLOTLY_COLORWAY, PLOTLY_CONTINUOUS_SCALE
from app.capabilities.monty.interpreter import DEFAULT_RESOURCE_LIMITS, MontyReplInterpreter
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
    assert "rlm" in help_text
    assert "visualizations" in help_text
    assert 'help("<collection-name>")' in help_text
    assert 'help("<tool-name>")' in help_text
    assert "wall-clock/timing primitives are unavailable" in help_text
    assert "`asyncio`" in help_text
    assert "math" in help_text
    assert "pandas" in help_text
    assert "use registered tools instead" in help_text
    assert "class definitions" in help_text
    assert "wildcard imports" in help_text
    assert "imports are no longer useful" in help_text
    assert "restart=True" in help_text
    assert "Python variables cannot be referenced" in help_text
    assert "preview_rows" in help_text
    assert "stack_metric_columns" in help_text


def test_monty_default_resource_limits_do_not_cap_duration() -> None:
    assert "max_duration_secs" not in DEFAULT_RESOURCE_LIMITS


@pytest.mark.anyio
async def test_monty_interpreter_persists_variables_between_calls() -> None:
    interpreter = MontyReplInterpreter(tools={})

    first = await interpreter.execute("x = 7\nlabel = 'ready'")
    second = await interpreter.execute("print(x)\nprint(label)")

    assert first.persisted_names == ["label", "x"]
    assert first.persistence_failures == []
    assert second.stdout == "7\nready\n"
    assert interpreter.state["x"] == 7
    assert interpreter.state["label"] == "ready"


@pytest.mark.anyio
async def test_monty_runtime_reports_persisted_variables(tmp_path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        chat_artifacts_dir=tmp_path / "data" / "chat_artifacts",
    )
    runtime = MontyPythonRuntime(TFRChatState(), settings)

    result = await runtime.execute("answer = 42")

    assert result["status"] == "success"
    assert result["variables"] == ["answer"]
    assert "persisted variable(s): answer" in result["summary"]


@pytest.mark.anyio
async def test_monty_runtime_restart_resets_repl_state(tmp_path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        chat_artifacts_dir=tmp_path / "data" / "chat_artifacts",
    )
    runtime = MontyPythonRuntime(TFRChatState(), settings)

    first = await runtime.execute("answer = 42")
    second = await runtime.execute("print(answer)", restart=True)

    assert first["status"] == "success"
    assert second["status"] == "error"
    assert "answer" in second["error"]


@pytest.mark.anyio
async def test_monty_runtime_returns_stdout_before_error(tmp_path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        chat_artifacts_dir=tmp_path / "data" / "chat_artifacts",
    )
    runtime = MontyPythonRuntime(TFRChatState(), settings)

    result = await runtime.execute('print("before")\n1 / 0')

    assert result["status"] == "error"
    assert result["stdout"] == "before\n"
    assert result["error_details"]["stdout_before_error"] == "before\n"
    assert result["error_details"]["error_type"] == "ZeroDivisionError"
    assert result["retryable"] is True
    assert "call python_repl_execute again" in result["model_guidance"]


def test_monty_help_accepts_multiple_targets(tmp_path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        chat_artifacts_dir=tmp_path / "data" / "chat_artifacts",
    )
    runtime = MontyPythonRuntime(TFRChatState(), settings)

    help_text = runtime.help(["handles", "create_line_chart"])

    assert "Collection: handles" in help_text
    assert "Tool: create_line_chart" in help_text
    assert "Valid plotly_kwargs keys for this tool" in help_text
    assert "\n\n---\n\n" in help_text


def test_monty_help_explains_sql_handle_flow_and_preview_escape_hatch(tmp_path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        chat_artifacts_dir=tmp_path / "data" / "chat_artifacts",
    )
    runtime = MontyPythonRuntime(TFRChatState(), settings)

    overview = runtime.help()
    describe_help = runtime.help("describe_dataset")
    preview_help = runtime.help("preview_dataset")

    assert runtime.registry.get("get_dataset") is None
    assert "SQL execute with persist_result=true" in overview
    assert "does not need a separate load/get step" in overview
    assert "Preview tools are for inspection only" in overview
    assert "SQL execute tool with persist_result=True" in describe_help
    assert "Return a text description" in describe_help
    assert "low-level dict tool" in preview_help
    assert "Prefer describe_dataset" in preview_help
    assert "does not return a dataframe" in preview_help
    assert "Do not build charts" in preview_help
    assert "preview_rows" in preview_help


def test_monty_rlm_help_lists_async_tools(tmp_path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        chat_artifacts_dir=tmp_path / "data" / "chat_artifacts",
    )
    runtime = MontyPythonRuntime(TFRChatState(), settings)

    help_text = runtime.help("rlm")

    assert "dataset_texts" in help_text
    assert "llm_query" in help_text
    assert "llm_query_batched" in help_text
    assert "await" in help_text


def test_monty_visualization_help_lists_valid_plotly_kwargs(tmp_path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        chat_artifacts_dir=tmp_path / "data" / "chat_artifacts",
    )
    runtime = MontyPythonRuntime(TFRChatState(), settings)

    line_help = runtime.help("create_line_chart")
    bar_help = runtime.help("create_bar_chart")

    assert "Valid plotly_kwargs keys for this tool" in line_help
    assert "markers" in line_help
    assert "line_shape" in line_help
    assert "color_continuous_scale" not in line_help
    assert "Any JSON-safe Figure.update_layout key is accepted" in line_help
    assert "color_continuous_scale" in bar_help


def test_monty_registered_tools_include_usage_examples(tmp_path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        chat_artifacts_dir=tmp_path / "data" / "chat_artifacts",
    )
    runtime = MontyPythonRuntime(TFRChatState(), settings)

    missing = [
        entry.name
        for entry in runtime.registry.entries()
        if not entry.usage_example
        or "```python" not in entry.usage_example
        or "# Prints" not in entry.usage_example
    ]

    assert missing == []


def test_monty_usage_examples_emit_balanced_markdown_fences(tmp_path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        chat_artifacts_dir=tmp_path / "data" / "chat_artifacts",
    )
    runtime = MontyPythonRuntime(TFRChatState(), settings)

    help_text = runtime.help(["group_by", "create_bar_chart"])
    fence_lines = [line for line in help_text.splitlines() if "```" in line]

    assert len(fence_lines) == 4
    assert fence_lines == ["```python", "```", "```python", "```"]
    assert "\nby_status = group_by" in help_text
    assert "\nchart = create_bar_chart" in help_text


def test_monty_viridis_palette_is_green_first() -> None:
    assert PLOTLY_COLORWAY[0] == "#fde725"
    assert PLOTLY_COLORWAY[-1] == "#440154"
    assert PLOTLY_CONTINUOUS_SCALE == "Viridis_r"


@pytest.mark.anyio
async def test_chat_agent_exposes_python_repl_tools_without_execute_conflict(tmp_path) -> None:
    settings = Settings(
        chat_model="test",
        monty_rlm_model="test",
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
    assert "python_repl_execute" in tool_names
    assert "python_repl_help" in tool_names


@pytest.mark.anyio
async def test_monty_tool_docstrings_populate_registered_schema(tmp_path) -> None:
    settings = Settings(
        chat_model="test",
        monty_rlm_model="test",
        data_dir=tmp_path / "data",
        chat_artifacts_dir=tmp_path / "data" / "chat_artifacts",
    )
    ctx = RunContext(
        deps=TFRChatDeps(TFRChatState(), settings=settings),
        model=TestModel(),
        usage=RunUsage(),
    )

    tools = await build_chat_agent(settings).toolsets[1].get_tools(ctx)

    help_tool = tools["python_repl_help"].tool_def
    execute_tool = tools["python_repl_execute"].tool_def

    assert "Python repl collections" in help_tool.description
    assert (
        "collection or tool name"
        in help_tool.parameters_json_schema["properties"]["name"]["description"]
    )
    assert "handles" in execute_tool.description
    code_description = execute_tool.parameters_json_schema["properties"]["code"]["description"]
    restart_description = execute_tool.parameters_json_schema["properties"]["restart"][
        "description"
    ]
    assert "Monty Python repl" in code_description
    assert "dataset or chart handle strings" in code_description
    assert "reset the REPL state" in restart_description


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
async def test_monty_runtime_resolves_bare_handle_aliases(tmp_path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        chat_artifacts_dir=tmp_path / "data" / "chat_artifacts",
    )
    state = TFRChatState()
    store = ChatArtifactStore(settings)
    store.save_dataset(
        state,
        columns=["category", "amount"],
        rows=[["A", 10], ["A", 15], ["B", 7]],
        label="Example rows",
        source="test",
    )
    runtime = MontyPythonRuntime(state, settings)

    result = await runtime.execute(
        """
counts = value_counts(ds_1, "category")
chart = create_bar_chart(ds_2, "category", "count", title="Counts")
emitted = emit_plotly_chart(chart)
print(emitted["component"])
"""
    )

    assert result["status"] == "success"
    assert result["stdout"] == "a2ui.PlotlyChart\n"
    assert [handle["handle"] for handle in result["handles"]] == ["ds_2", "fig_1"]
    assert state.components[-1].type == "a2ui.PlotlyChart"


@pytest.mark.anyio
async def test_monty_describe_tools_return_strings_for_handle_inspection(tmp_path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        chat_artifacts_dir=tmp_path / "data" / "chat_artifacts",
    )
    state = TFRChatState()
    store = ChatArtifactStore(settings)
    dataset_handle = store.save_dataset(
        state,
        columns=["status", "amount"],
        rows=[["open", 1200], ["closed", 500]],
        label="Claims",
        source="sql",
    ).handle
    runtime = MontyPythonRuntime(state, settings)

    result = await runtime.execute(
        f"""
handles = describe_handles()
handle_summary = describe_handle({dataset_handle!r})
dataset_summary = describe_dataset({dataset_handle!r}, limit=1)
print(handles)
print(handle_summary)
print(dataset_summary)
"""
    )

    assert result["status"] == "success"
    assert "ds_1: dataset; label='Claims'; shape=2x2; source=sql" in result["stdout"]
    assert "Dataset handle: ds_1" in result["stdout"]
    assert "Columns: status, amount" in result["stdout"]
    assert '"amount": 1200' in result["stdout"]


@pytest.mark.anyio
async def test_monty_stack_metric_columns_prepares_stacked_bar_dataset(tmp_path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        chat_artifacts_dir=tmp_path / "data" / "chat_artifacts",
    )
    state = TFRChatState()
    store = ChatArtifactStore(settings)
    dataset_handle = store.save_dataset(
        state,
        columns=["reference_policy", "items_completed", "items_other"],
        rows=[
            ["prefer_r2", 8, 2],
            ["prefer_r2", 3, 1],
            ["prefer_r1", 5, 4],
        ],
        label="Policy metrics",
        source="test",
    ).handle
    runtime = MontyPythonRuntime(state, settings)

    result = await runtime.execute(
        f"""
stacked = stack_metric_columns(
    {dataset_handle!r},
    "reference_policy",
    ["items_completed", "items_other"],
)
chart = create_bar_chart(
    stacked,
    "reference_policy",
    "value",
    color="metric",
    title="Completed vs other by reference_policy",
    plotly_kwargs={{"barmode": "stack", "text_auto": True}},
)
emit_plotly_chart(chart)
"""
    )

    assert result["status"] == "success"
    stacked_handle = result["handles"][0]["handle"]
    stacked = store.load_dataset(state, stacked_handle)
    assert stacked.columns == ["reference_policy", "metric", "value"]
    assert sorted(stacked.rows) == [
        ["prefer_r1", "items_completed", 5],
        ["prefer_r1", "items_other", 4],
        ["prefer_r2", "items_completed", 11],
        ["prefer_r2", "items_other", 3],
    ]
    assert state.components[-1].type == "a2ui.PlotlyChart"


@pytest.mark.anyio
async def test_monty_charts_accept_preview_handles_and_direct_plotly_kwargs(tmp_path) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        chat_artifacts_dir=tmp_path / "data" / "chat_artifacts",
    )
    state = TFRChatState()
    store = ChatArtifactStore(settings)
    ds1 = store.save_dataset(
        state,
        columns=["status", "cnt"],
        rows=[["complete", 8], ["pending", 2]],
        label="Audit batch status counts",
        source="test",
    ).handle
    ds2 = store.save_dataset(
        state,
        columns=["model_name", "status", "cnt"],
        rows=[["gpt-5", "complete", 6], ["gpt-5", "failed", 1]],
        label="Eval run status by model",
        source="test",
    ).handle
    ds3 = store.save_dataset(
        state,
        columns=["reference_kind", "avg_score", "n", "min_score", "max_score"],
        rows=[["r1", 0.72, 5, 0.2, 1.0], ["r2", 0.84, 7, 0.5, 1.0]],
        label="Reference kind scores",
        source="test",
    ).handle
    runtime = MontyPythonRuntime(state, settings)

    result = await runtime.execute(
        f"""
ds1 = preview_dataset({ds1!r})
ds2 = preview_dataset({ds2!r})
ds3 = preview_dataset({ds3!r})

chart1 = create_bar_chart(ds1, x="status", y="cnt", title="Audit batch status counts")
emit_plotly_chart(chart1)

chart2 = create_bar_chart(
    ds2,
    x="model_name",
    y="cnt",
    color="status",
    barmode="group",
    title="Eval runs: model_name x status",
)
emit_plotly_chart(chart2)

chart3 = create_bar_chart(
    ds3,
    x="reference_kind",
    y="avg_score",
    title="Avg eval_comparisons score by reference kind",
)
emit_plotly_chart(chart3)

chart4 = create_scatter_plot(
    ds3,
    x="min_score",
    y="max_score",
    title="Min vs Max score by reference kind",
    text="reference_kind",
)
emit_plotly_chart(chart4)

print("done")
"""
    )

    assert result["status"] == "success"
    assert result["stdout"] == "done\n"
    emitted_charts = [
        component for component in state.components if component.type == "a2ui.PlotlyChart"
    ]
    assert len(emitted_charts) == 4
    assert store.load_plotly_chart(state, state.handles[-1].handle).figure["data"][0]["text"] == [
        "r1",
        "r2",
    ]


@pytest.mark.anyio
async def test_monty_runtime_errors_are_concise_and_repl_recovers(tmp_path) -> None:
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
            label="Example rows",
            source="test",
        )
        .handle
    )
    runtime = MontyPythonRuntime(state, settings)

    failed = await runtime.execute(
        f"""
chart = create_bar_chart({dataset_handle!r}, x_col="category", y="amount")
"""
    )
    recovered = await runtime.execute(
        f"""
chart = create_bar_chart({dataset_handle!r}, "category", "amount", title="Amounts")
emitted = emit_plotly_chart(chart)
"""
    )

    assert failed["status"] == "error"
    assert "missing 1 required positional argument: 'x'" in failed["error"]
    assert "Traceback" not in failed["error"]
    assert failed["traceback"] is None
    assert failed["error_details"]["error_type"] == "TypeError"
    assert failed["retryable"] is True
    assert "call python_repl_execute again" in failed["model_guidance"]
    assert recovered["status"] == "success"
    assert state.components[-1].type == "a2ui.PlotlyChart"


@pytest.mark.anyio
async def test_monty_execute_status_uses_generic_failure_message(tmp_path) -> None:
    settings = Settings(
        chat_model="test",
        monty_rlm_model="test",
        data_dir=tmp_path / "data",
        chat_artifacts_dir=tmp_path / "data" / "chat_artifacts",
    )
    state = TFRChatState()
    ctx = RunContext(
        deps=TFRChatDeps(state, settings=settings),
        model=TestModel(),
        usage=RunUsage(),
    )
    toolset = MontyPythonCapability().get_toolset()
    tools = await toolset.get_tools(ctx)

    failed = await toolset.call_tool(
        "python_repl_execute",
        {"code": "1 / 0"},
        ctx,
        tools["python_repl_execute"],
    )
    assert failed.return_value["status"] == "error"
    assert failed.return_value["error"] == "ZeroDivisionError: division by zero"
    assert state.status == "using_tools"
    assert state.error_message is None
    assert state.current_step == "Python repl execution failed."

    recovered = await toolset.call_tool(
        "python_repl_execute",
        {"code": 'print("ok")'},
        ctx,
        tools["python_repl_execute"],
    )

    assert state.error_message is None
    assert recovered.return_value["status"] == "success"
    assert recovered.return_value["stdout"] == "ok\n"


@pytest.mark.anyio
async def test_monty_rlm_tools_create_texts_and_run_batched_queries(tmp_path) -> None:
    settings = Settings(
        chat_model="test",
        monty_rlm_model="test",
        data_dir=tmp_path / "data",
        chat_artifacts_dir=tmp_path / "data" / "chat_artifacts",
    )
    state = TFRChatState()
    dataset_handle = (
        ChatArtifactStore(settings)
        .save_dataset(
            state,
            columns=["claim", "note"],
            rows=[
                ["A1", "The roof was damaged by hail."],
                ["B2", "The window seal failed over time."],
            ],
            label="Claim notes",
            source="test",
        )
        .handle
    )
    runtime = MontyPythonRuntime(state, settings)

    result = await runtime.execute(
        f"""
notes = dataset_texts({dataset_handle!r}, "note")
claims = dataset_texts({dataset_handle!r}, "claim")
print(claims[0])
texts = notes
prompts = ["Summarize this claim note: " + text for text in texts]
answers = await llm_query_batched(prompts)
print(len(answers))
print(answers[0])
"""
    )

    assert result["status"] == "success"
    assert result["stdout"] == "A1\n2\nRLM test response\n"
    assert result["variables"] == ["answers", "claims", "notes", "prompts", "texts"]
    assert result["rlm"]["call_count"] == 2
    assert result["rlm"]["usage"]["requests"] == 2
    assert result["rlm"]["usage"]["total_tokens"] > 0
    assert "used 2 sub-LLM call(s)" in result["summary"]


@pytest.mark.anyio
async def test_monty_rlm_tools_enforce_call_budget_and_restart_resets(tmp_path) -> None:
    settings = Settings(
        chat_model="test",
        monty_rlm_model="test",
        monty_rlm_max_llm_calls=2,
        data_dir=tmp_path / "data",
        chat_artifacts_dir=tmp_path / "data" / "chat_artifacts",
    )
    runtime = MontyPythonRuntime(TFRChatState(), settings)

    first = await runtime.execute(
        """
answers = await llm_query_batched(["one", "two"])
print(len(answers))
"""
    )
    blocked = await runtime.execute('answer = await llm_query("three")')
    after_restart = await runtime.execute('answer = await llm_query("fresh")', restart=True)

    assert first["status"] == "success"
    assert first["rlm"]["call_count"] == 2
    assert blocked["status"] == "error"
    assert "LLM call limit exceeded" in blocked["error"]
    assert blocked["rlm"]["call_count"] == 2
    assert after_restart["status"] == "success"
    assert after_restart["rlm"]["call_count"] == 1


@pytest.mark.anyio
async def test_visualization_tools_accept_extra_plotly_and_layout_kwargs(tmp_path) -> None:
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
async def test_visualization_tools_reject_plotly_kwargs_that_override_named_args(
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
    assert "Use the named tool arguments" in result["error"]
    assert "x" in result["error"]


@pytest.mark.anyio
async def test_visualization_tools_reject_unsupported_plotly_kwargs(tmp_path) -> None:
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
