"""Prompt and help text for the lightweight Monty Python repl."""

from __future__ import annotations

from app.capabilities.monty.registry import FunctionRegistry, RegisteredFunction

HelpTarget = str | list[str] | None


def render_python_repl_guidance(help_name: str = "help") -> str:
    """Render shared Python repl guidance with the caller's help function name."""

    return (
        "A Monty Python repl is available for composing dataframe handle operations, "
        "Plotly visualizations, and sub-LLM text analysis.\n"
        "Discovery flow:\n"
        f"- Call {help_name}() to see all collections.\n"
        f'- Call {help_name}("<collection-name>"), or a list of collections, to see '
        "available tools for the collection(s).\n"
        f'- Call {help_name}("<tool-name>"), or a list of tools, to see detailed docs '
        "before executing code.\n"
        "Use discovery instead of guessing collection names, tool names, signatures, "
        "valid kwargs, or return values. The repl uses Monty, a restricted subset of "
        "Python. Class definitions are not supported, wildcard imports are not "
        "supported, and third-party libraries cannot be imported. Importable standard "
        "library modules include `sys`, `typing`, `asyncio`, `math`, `json`, `re`, "
        "`datetime`, `os`, and `pathlib`; `os` and `pathlib` are intentionally "
        "limited, so prefer pure string/path manipulation unless a registered tool's "
        "help says otherwise. Import standard modules at the top of the snippet before "
        "use. Wall-clock and timing primitives such as `asyncio.sleep`, "
        "`datetime.datetime.now()`, `datetime.date.today()`, and the `time` module are "
        "unavailable. Keep data behind handles returned by SQL or Python repl tools. "
        "The normal data path is: use SQL execute with persist_result=true to read "
        "database rows and receive a dataset_handle; inside the Python repl, assign "
        "that handle string to a variable if useful, then pass the handle directly to "
        "dataframe and visualization tools. The Python repl does not need a separate "
        "load/get step and does not expose SQL tables as Python variables. Registered "
        "tools are injected directly into the repl namespace, so call them directly "
        "without imports. Variables assigned in one python_repl_execute call remain "
        "available to later Python repl executions in the same artifact session; they "
        "are convenient for intermediate handle strings, chart handles, scalar "
        "settings, and small derived values. Pass `restart=True` to "
        "`python_repl_execute` to reset REPL state when prior variables or imports are "
        "no longer useful. Prefer text-returning inspection tools when a human-readable "
        "summary is enough. Use structured preview tools only when code needs fields "
        "such as columns, row_count, or preview_rows; previews do not return a "
        "dataframe, complete dataset, or new handle. Do not build charts or "
        "transformed datasets from preview_rows. For real data prep, pass the original "
        "dataset handle to dataframe tools, then pass the resulting handle to "
        "visualization tools. Python repl variables are not SQL database tables and "
        "cannot be referenced from SQL tools. Scientific and dataframe libraries such "
        "as `pandas`, `numpy`, `scipy`, and `plotly` are not available inside Python "
        "repl code. Use registered dataframe and visualization tools instead of "
        "importing those libraries. Async tools must be called with `await`; calling "
        "them without `await` returns an unresolved future, not the value. Sub-LLM "
        "calls share a configured call budget for the artifact session; use Python for "
        "grouping, filtering, and aggregation before spending that budget. Synchronous "
        "tools are called directly. When submitting nested strings, assign multiline "
        "code to variables first and avoid escape-heavy inline snippets."
    )


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
