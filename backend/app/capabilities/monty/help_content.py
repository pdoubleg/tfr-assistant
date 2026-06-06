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
        visualizations, sub-LLM text analysis, and output bundle generation.

        **Discovery flow**
        - Call `{help_name}()` to see all collections.
        - Call `{help_name}("<collection-name>")`, or a list of collections, for
          ready-to-use tool docs with signatures, arguments, returns, and examples.
        - Call `{help_name}("<tool-name>")`, or a list of tools, when you only need
          surgical details for specific calls you plan to execute.

        Use discovery instead of guessing names, signatures, kwargs, or return values.
        Use exactly the parameter names shown in the help signature. Args not listed
        are invalid; for example, `group_by()` uses `by`, not pandas-style `keys`.
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

        **Output generation routing**
        - Use `report_bundles` for reports, findings memos, printable/browser HTML,
          analysis packets, and evidence-heavy audit summaries.
        - Use `deck_bundles` for slides, PowerPoint, PPTX, presentations, executive
          briefings, board decks, and meeting-ready materials.
        - Both paths save a data workbook for referenced datasets. Load only the chosen
          collection help unless the user asks for both a report and a deck.
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
        f"## No Monty Help Target: `{name}`\n\n"
        "No collection or tool with that exact name is registered.\n\n"
        f"**Collections:** {collections}\n\n"
        f"**Tools:** {functions}\n\n"
        "**Next step:** call `help()` for the overview, or call "
        '`help("<collection-name>")` with one of the collection names above.'
    )


def _render_overview(registry: FunctionRegistry) -> str:
    blocks = ["# Monty Python Repl Overview", "", PYTHON_REPL_GUIDANCE, "", "## Collections"]
    for collection in registry.collections():
        tools = ", ".join(collection.sorted_tool_names())
        blocks.append(f"- `{collection.name}`: {collection.description} Tools: {tools}")
    blocks.extend(
        [
            "",
            "## Next Step",
            'Call `help("<collection-name>")` for the collection most relevant to the task. '
            'If you already know the exact tools to chain, call `help(["tool_a", "tool_b"])` '
            "to get only those tool-level details before executing code.",
        ]
    )
    return "\n".join(blocks)


def _render_collection(registry: FunctionRegistry, name: str) -> str:
    collection = registry.get_collection(name)
    if collection is None:
        return render_help(registry, name)
    lines = [
        f"## Collection: {collection.name}",
        "",
        collection.description,
        "",
        "This collection view includes enough detail to call its tools directly. Use the exact "
        "parameter names shown in each signature; unlisted aliases are invalid.",
        "",
        "### Tools",
    ]
    for function in registry.entries(collection=name):
        lines.extend(["", *_render_tool_card(function, include_details=False)])
    lines.extend(
        [
            "",
            "### Next Step",
            "Use `python_repl_execute` with the exact signatures above. If you need to combine "
            'tools from multiple collections, call `help(["tool_a", "tool_b"])` for just '
            "those tool details.",
        ]
    )
    return "\n".join(lines)


def _render_function(function: RegisteredFunction) -> str:
    lines = [
        f"## Tool: {function.name}",
        f"Collection: {function.collection or 'ungrouped'}",
        "",
        *_render_tool_card(function, include_details=True),
        "",
        "### Next Step",
        "Call `python_repl_execute` with this exact signature. Do not add aliases or kwargs "
        "that are not listed above. When chaining several tools, you can call "
        '`help(["tool_a", "tool_b"])` first to keep only the needed docs in context.',
    ]
    return "\n".join(lines)


def _render_tool_card(
    function: RegisteredFunction,
    *,
    include_details: bool,
) -> list[str]:
    lines = [
        f"#### `{function.name}`",
        "",
        function.detailed_description if include_details else function.description,
        "",
        "**Signature**",
        "",
        f"    {function.render_signature(multiline=False)}",
        "",
        "**Arguments**",
    ]
    if function.arguments:
        lines.extend(argument.render_argument_help() for argument in function.arguments)
    else:
        lines.append("- None")
    if function.return_description or function.return_annotation:
        lines.extend(["", "**Returns**"])
        return_line = function.return_annotation or "value"
        if function.return_description:
            return_line += f": {function.return_description}"
        lines.append(f"- {return_line}")
    if function.usage_example:
        lines.extend(["", "**Example**", "", function.usage_example])
    return lines
