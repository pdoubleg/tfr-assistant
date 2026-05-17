"""Prompt and help text for the lightweight Monty Python repl."""

from __future__ import annotations

from textwrap import dedent

from app.capabilities.monty.registry import FunctionRegistry, RegisteredFunction

HelpTarget = str | list[str] | None


def render_python_repl_guidance(help_name: str = "help") -> str:
    """Render shared Python repl guidance with the caller's help function name."""

    return dedent(
        f"""\
        A Monty Python repl is available for dataframe handle operations, Plotly
        visualizations, and sub-LLM text analysis.
        Discovery flow:
        - Call {help_name}() to see all collections.
        - Call {help_name}("<collection-name>"), or a list of collections, to see
          tools in the collection(s).
        - Call {help_name}("<tool-name>"), or a list of tools, to see detailed docs
          before executing code.

        Use discovery instead of guessing names, signatures, kwargs, or return values.
        Registered tools, including collection tools, are injected directly into the repl
        namespace; call them without imports. A single code block can chain multiple
        calls, pass one tool's returned handle into another, and produce a final chart,
        dataset, or text result. For uncertain work, call one function at a time to
        inspect output before moving to the next step. Choose the style that best fits
        the task.

        Keep data behind string handles returned by SQL or repl tools. The normal data path is
        SQL execute with persist_result=true -> dataset_handle -> dataframe tools ->
        visualization tools. The repl does not need a separate load/get step, does not
        expose SQL tables as Python variables, and Python variables cannot be referenced
        from SQL tools. Preview tools are for inspection only; do not build charts or
        transformed datasets from preview_rows.

        Monty is a restricted Python subset: class definitions, wildcard imports,
        third-party libraries, `time`, and wall-clock/timing primitives are unavailable.
        Importable standard modules include `sys`, `typing`, `asyncio`, `math`, `json`,
        `re`, `datetime`, `os`, and `pathlib`; `os` and `pathlib` are limited. Scientific
        and dataframe libraries such as `pandas`, `numpy`, `scipy`, and `plotly` are not
        available; use registered tools instead. Await async tools, call sync tools
        directly, and use `restart=True` to reset repl state when prior variables or
        imports are no longer useful. Sub-LLM calls share a session budget, so use
        Python for grouping, filtering, and aggregation before spending that budget.
        """
    ).strip()


PYTHON_REPL_GUIDANCE = render_python_repl_guidance()


def render_help(registry: FunctionRegistry, name: HelpTarget = None) -> str:
    if name is None:
        return _render_overview(registry)
    if isinstance(name, list):
        if not name:
            return _render_overview(registry)
        return "\n\n---\n\n".join(render_help(registry, target) for target in name)
    collection = registry.get_collection(name)
    if collection:
        return _render_collection(registry, name)
    function = registry.get(name)
    if function:
        return _render_function(function)
    collections = ", ".join(item.name for item in registry.collections())
    functions = ", ".join(item.name for item in registry.entries())
    return (
        f"No collection or tool named {name!r} is registered.\n\n"
        f"Collections: {collections}\n\nTools: {functions}"
    )


def _render_overview(registry: FunctionRegistry) -> str:
    blocks = ["Monty Python Repl Overview", "", PYTHON_REPL_GUIDANCE, "", "Collections:"]
    for collection in registry.collections():
        tools = ", ".join(collection.sorted_tool_names())
        blocks.append(f"- {collection.name}: {collection.description} Tools: {tools}")
    return "\n".join(blocks)


def _render_collection(registry: FunctionRegistry, name: str) -> str:
    collection = registry.get_collection(name)
    if collection is None:
        return render_help(registry, name)
    lines = [
        f"Collection: {collection.name}",
        "",
        collection.description,
        "",
        "Available tools:",
    ]
    for function in registry.entries(collection=name):
        lines.append(f"- {function.render_signature(multiline=False)}")
        lines.append(f"  {function.description}")
    return "\n".join(lines)


def _render_function(function: RegisteredFunction) -> str:
    lines = [
        f"Tool: {function.name}",
        f"Collection: {function.collection or 'ungrouped'}",
        "",
        function.detailed_description or function.description,
        "",
        "Signature:",
        function.render_signature(multiline=True),
        "",
        "Arguments:",
    ]
    if function.arguments:
        lines.extend(argument.render_argument_help() for argument in function.arguments)
    else:
        lines.append("- None")
    if function.return_description or function.return_annotation:
        lines.extend(["", "Returns:"])
        return_line = function.return_annotation or "value"
        if function.return_description:
            return_line += f": {function.return_description}"
        lines.append(f"- {return_line}")
    if function.usage_example:
        lines.extend(["", "Examples:", function.usage_example])
    return "\n".join(lines)
