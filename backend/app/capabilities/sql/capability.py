"""Pydantic AI capability exposing safe SQL database tools."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Literal

from ag_ui.core import EventType, StateSnapshotEvent
from pydantic_ai import FunctionToolset, RunContext, ToolReturn
from pydantic_ai.capabilities import AbstractCapability

from app.capabilities.deps import TFRChatDeps
from app.capabilities.sql.backend import SQLDatabase, SQLDatabaseError, create_sql_database
from app.capabilities.sql.safety import SQLSafetyError, validate_readonly_query
from app.capabilities.sql.types import ForeignKeyInfo, QueryResult, SchemaInfo, TableInfo
from app.db.session import engine
from app.models.chat_state import SelectedHomeRowContext, TFRChatState
from app.presenters.a2ui import generate_data_table
from app.services.chat_artifacts import ChatArtifactStore
from app.services.status_reporter import ChatStateStatusReporter

SQLScope = Literal["full", "selected"]


@dataclass(slots=True)
class SQLDatabaseCapability(AbstractCapability[TFRChatDeps]):
    """Bundle database inspection, SQL execution tools, and SQL-specific instructions."""

    max_display_rows: int = 10000
    max_agent_rows: int = 100
    default_agent_limit: int = 10

    def get_instructions(self):
        def instructions(_ctx: RunContext[TFRChatDeps]) -> str:
            database = _database()
            return (
                "Database tools are available for read-only analytics over the TFR "
                "application database. Start with get_tables and get_schema or "
                "get_table_info before writing SQL. Use execute for SELECT/WITH queries "
                "only. execute has scope='full' for the whole database and "
                "scope='selected' for homepage selections. Before using scope='selected', "
                "call get_selected_rows_info to inspect the selected_home_rows virtual "
                "table, join keys, and examples. For selected scope, write SQL that "
                "references the selected_home_rows CTE. Use the limit parameter to "
                "control how many preview rows are returned to you. execute has "
                "render_table=false by default; keep it false "
                "for intermediate analysis and ordinary reasoning. Set render_table=true "
                "only when the user asks to see rows or a table, or when a rendered table "
                "is obviously the clean final answer. Otherwise answer from the preview "
                "and ask whether the user wants the result table shown. execute has "
                "persist_result=false by default. Set persist_result=true only when a "
                "downstream table, chart, or Python sandbox step needs a durable dataset "
                "handle for the full result. Python sandbox variables and handles created "
                "inside python_sandbox_execute are not database tables and are not visible "
                "to SQL; SQL can only query the configured application database plus the "
                "selected_home_rows CTE when scope='selected'. "
                f"{database.prompt_instructions}"
            )

        return instructions

    def get_toolset(self) -> FunctionToolset[TFRChatDeps]:
        toolset = FunctionToolset[TFRChatDeps](
            id="sql_database",
            instructions=(
                "Use these read-only SQL tools for database discovery and analytics. "
                "Never guess table relationships; inspect schema and foreign keys first. "
                "Do not reference Python sandbox variables or Monty-created handles in SQL; "
                "they are not present in the database."
            ),
        )

        @toolset.tool
        async def get_tables(ctx: RunContext[TFRChatDeps]) -> ToolReturn:
            """List database tables available to query.

            Use this before writing SQL when you need to discover the available
            tables in the application database.

            Returns:
                A markdown bullet list of table names.
            """

            reporter = _reporter(ctx, "sql_get_tables")
            reporter.in_progress("Reading database table list...", progress=20)
            database = _database()
            tables = await database.get_tables()
            reporter.completed(f"Loaded {len(tables)} database table(s).", progress=100)
            _mark_complete(ctx.deps.state)
            return _tool_return(ctx.deps.state, "\n".join(f"- {table}" for table in tables))

        @toolset.tool
        async def get_table_info(ctx: RunContext[TFRChatDeps], table_name: str) -> ToolReturn:
            """Inspect one table's columns, keys, foreign keys, and indexes.

            Args:
                table_name: Exact table name to inspect. Prefer choosing this from
                    get_tables or get_schema output instead of guessing.

            Returns:
                A text description of the table columns, primary key columns,
                outgoing foreign keys, and indexes. Returns a not-found message
                when the table does not exist.
            """

            reporter = _reporter(ctx, "sql_get_table_info")
            reporter.in_progress(f"Inspecting table {table_name}...", progress=25)
            table = await _database().get_table_info(table_name)
            if table is None:
                reporter.completed(f"Table {table_name} was not found.", progress=100)
                _mark_complete(ctx.deps.state)
                return _tool_return(ctx.deps.state, f"Table '{table_name}' was not found.")
            reporter.completed(f"Loaded table info for {table_name}.", progress=100)
            _mark_complete(ctx.deps.state)
            return _tool_return(ctx.deps.state, _format_table_info(table))

        @toolset.tool
        async def get_schema(ctx: RunContext[TFRChatDeps]) -> ToolReturn:
            """Inspect the full database schema.

            Use this when you need broad schema context before joining tables or
            choosing which table should answer the user's question.

            Returns:
                A text schema overview for every database table, including
                columns, primary keys, foreign keys, and indexes.
            """

            reporter = _reporter(ctx, "sql_get_schema")
            reporter.in_progress("Inspecting database schema...", progress=20)
            schema = await _database().get_schema()
            reporter.completed(f"Loaded schema for {len(schema.tables)} table(s).", progress=100)
            _mark_complete(ctx.deps.state)
            return _tool_return(ctx.deps.state, _format_schema(schema))

        @toolset.tool
        async def get_selected_rows_info(ctx: RunContext[TFRChatDeps]) -> ToolReturn:
            """Describe the selected_home_rows virtual table for selected-scope SQL.

            Call this before using execute or explain with scope="selected". It
            tells you whether homepage rows are selected, which columns are
            available in the selected_home_rows CTE, and the safest join patterns
            to constrain real database tables to the current selection.

            Returns:
                A text guide containing the selected row count, CTE columns,
                common join recipes, and a small sample of selected row values.
            """

            reporter = _reporter(ctx, "sql_get_selected_rows_info")
            reporter.in_progress("Reading selected row SQL context...", progress=20)
            selected_rows = _selected_rows(ctx.deps.state)
            message = _format_selected_rows_info(selected_rows)
            reporter.completed(
                f"Loaded selected row SQL context for {len(selected_rows)} row(s).",
                progress=100,
            )
            _mark_complete(ctx.deps.state)
            return _tool_return(ctx.deps.state, message)

        @toolset.tool
        async def explain(
            ctx: RunContext[TFRChatDeps],
            sql: str,
            scope: SQLScope = "full",
        ) -> ToolReturn:
            """Explain a read-only SQL query plan without returning data rows.

            Args:
                sql: A SELECT or WITH query to explain. Do not include write,
                    schema, transaction, or administrative statements.
                scope: Query scope. Use "full" for the whole database. Use
                    "selected" only when the query references the selected_home_rows
                    CTE to constrain analysis to homepage-selected rows.

            Returns:
                The database query plan as text, or a validation error if the SQL
                is unsafe or the selected scope is malformed.
            """

            reporter = _reporter(ctx, "sql_explain")
            reporter.in_progress("Explaining SQL query plan...", progress=35)
            try:
                effective_sql = _effective_sql_for_scope(ctx.deps.state, sql, scope)
                plan = await _database().explain(effective_sql)
            except (SQLSafetyError, ValueError, SQLDatabaseError) as exc:
                message = _format_sql_error_for_agent("explain", exc, sql=sql)
                reporter.error(_sql_error_status("explain", exc), progress=100)
                return _tool_return(ctx.deps.state, message)
            reporter.completed("SQL query plan is ready.", progress=100)
            _mark_complete(ctx.deps.state)
            return _tool_return(ctx.deps.state, plan)

        @toolset.tool
        async def get_foreign_keys(
            ctx: RunContext[TFRChatDeps],
            table_name: str,
        ) -> ToolReturn:
            """List outgoing foreign keys declared by a table.

            Args:
                table_name: Exact table name whose declared foreign keys should
                    be inspected.

            Returns:
                A text list of foreign key relationships from this table to
                referred tables, or a message saying none were found.
            """

            reporter = _reporter(ctx, "sql_get_foreign_keys")
            reporter.in_progress(f"Reading foreign keys for {table_name}...", progress=30)
            keys = await _database().get_foreign_keys(table_name)
            reporter.completed(f"Loaded {len(keys)} foreign key relationship(s).", progress=100)
            _mark_complete(ctx.deps.state)
            return _tool_return(ctx.deps.state, _format_foreign_keys(keys))

        @toolset.tool
        async def get_related_tables(
            ctx: RunContext[TFRChatDeps],
            table_name: str,
        ) -> ToolReturn:
            """Find tables related to a table through foreign keys.

            Args:
                table_name: Exact table name to use as the relationship anchor.

            Returns:
                A text list of incoming and outgoing foreign key relationships
                involving the requested table.
            """

            reporter = _reporter(ctx, "sql_get_related_tables")
            reporter.in_progress(f"Finding tables related to {table_name}...", progress=30)
            keys = await _database().get_related_tables(table_name)
            reporter.completed(f"Loaded {len(keys)} related table relationship(s).", progress=100)
            _mark_complete(ctx.deps.state)
            return _tool_return(ctx.deps.state, _format_foreign_keys(keys))

        @toolset.tool
        async def execute(
            ctx: RunContext[TFRChatDeps],
            sql: str,
            limit: int = self.default_agent_limit,
            scope: SQLScope = "full",
            render_table: bool = False,
            persist_result: bool = False,
        ) -> ToolReturn:
            """Execute a safe read-only SQL query.

            Use this for SELECT or WITH queries after inspecting schema. The SQL
            should include its own WHERE/LIMIT clauses when needed for correctness
            or performance. Python sandbox variables and handles created by
            python_sandbox_execute are not SQL tables and cannot be referenced
            here.

            Args:
                sql: A read-only SELECT or WITH query. Do not include write,
                    schema, transaction, or administrative statements.
                limit: Maximum number of result rows returned to you for reasoning.
                    Defaults to 10 and is capped by the backend. This does not add
                    or replace a SQL LIMIT clause.
                scope: Query scope. Use "full" for the whole database. Use
                    "selected" when the user asks about homepage-selected rows; in
                    that case the SQL must reference the selected_home_rows CTE.
                render_table: Whether to emit the result as a table component in
                    the chat UI. Defaults to false. Prefer false for intermediate
                    analysis and normal answers; set true only when the user asks
                    to see rows/a table or the table is clearly the final answer.
                persist_result: Whether to save the full displayed query result as
                    a dataset handle for downstream Python sandbox transforms or
                    Plotly charts. Defaults to false for exploratory queries.

            Returns:
                A JSON preview of the result columns and up to limit rows for
                reasoning. When render_table is true, also emits a chat table
                component containing the rendered result rows. When persist_result
                is true, returns a dataset_handle for the persisted result.
            """

            reporter = _reporter(ctx, "sql_execute")
            reporter.in_progress(f"Executing SQL query with preview limit {limit}...", progress=40)
            try:
                effective_sql = _effective_sql_for_scope(ctx.deps.state, sql, scope)
                result = await _database(
                    max_display_rows=self.max_display_rows,
                    max_agent_rows=self.max_agent_rows,
                ).execute(effective_sql, agent_limit=limit, scope=scope)
            except (SQLSafetyError, ValueError, SQLDatabaseError) as exc:
                message = _format_sql_error_for_agent("execute", exc, sql=sql)
                reporter.error(_sql_error_status("execute", exc), progress=100)
                return _tool_return(ctx.deps.state, message)

            if render_table:
                _append_query_components(ctx.deps.state, result)
            dataset_handle = None
            if persist_result:
                artifact = ChatArtifactStore(ctx.deps.settings).save_dataset(
                    ctx.deps.state,
                    columns=result.columns,
                    rows=result.rows,
                    label=_result_caption(result),
                    source="sql",
                )
                dataset_handle = artifact.handle
            reporter.completed(
                _result_status(
                    result,
                    table_rendered=render_table,
                    dataset_handle=dataset_handle,
                ),
                progress=100,
            )
            _mark_complete(ctx.deps.state)
            return _tool_return(
                ctx.deps.state,
                _format_query_result_for_agent(
                    result,
                    table_rendered=render_table,
                    dataset_handle=dataset_handle,
                ),
            )

        return toolset


def _database(max_display_rows: int = 1000, max_agent_rows: int = 100) -> SQLDatabase:
    return create_sql_database(
        engine=engine,
        max_display_rows=max_display_rows,
        max_agent_rows=max_agent_rows,
    )


def _reporter(ctx: RunContext[TFRChatDeps], source_name: str) -> ChatStateStatusReporter:
    return ChatStateStatusReporter(ctx.deps.state, source_name=source_name)


def _tool_return(state: TFRChatState, return_value: str) -> ToolReturn:
    return ToolReturn(
        return_value=return_value,
        metadata=[StateSnapshotEvent(type=EventType.STATE_SNAPSHOT, snapshot=state)],
    )


def _mark_complete(state: TFRChatState) -> None:
    state.status = "complete"
    state.progress = max(state.progress, 100)


def _format_table_info(table: TableInfo) -> str:
    lines = [f"Table: {table.name}", "", "Columns:"]
    for column in table.columns:
        flags = []
        if column.primary_key:
            flags.append("primary key")
        if not column.nullable:
            flags.append("not null")
        suffix = f" ({', '.join(flags)})" if flags else ""
        lines.append(f"- {column.name}: {column.type}{suffix}")
    if table.foreign_keys:
        lines.extend(["", "Foreign keys:", _format_foreign_keys(table.foreign_keys)])
    if table.indexes:
        lines.append("")
        lines.append("Indexes:")
        lines.extend(
            f"- {index.name}: {', '.join(index.columns)}{' (unique)' if index.unique else ''}"
            for index in table.indexes
        )
    return "\n".join(lines)


def _format_schema(schema: SchemaInfo) -> str:
    return "\n\n".join(_format_table_info(table) for table in schema.tables)


def _selected_rows(state: TFRChatState) -> list[SelectedHomeRowContext]:
    return list(state.run_context.selected_home_rows) if state.run_context else []


def _format_selected_rows_info(selected_rows: list[SelectedHomeRowContext]) -> str:
    columns = _selected_rows_columns()
    lines = [
        "selected_home_rows is a temporary CTE available only when execute/explain "
        "uses scope='selected'.",
        f"Currently selected rows: {len(selected_rows)}",
        "",
        "Columns:",
        *[f"- {column}" for column in columns],
        "",
        "Common joins:",
        "- audit_reviews: selected_home_rows.review_id = audit_reviews.id",
        "- review/result projection tables: selected_home_rows.review_id = <table>.review_id",
        "- batch tables: selected_home_rows.batch_id = <table>.id when joining to batch records",
        "- form-scoped queries: selected_home_rows.form_id/form_version can "
        "constrain form tables or result versions",
        "",
        "Selected-scope query pattern:",
        "SELECT ...",
        "FROM selected_home_rows shr",
        "JOIN audit_reviews ar ON ar.id = shr.review_id",
        "JOIN ...",
        "",
        "Rules:",
        "- Use scope='selected' only when the SQL references selected_home_rows.",
        "- Use scope='full' for whole-database questions or comparisons.",
    ]
    if selected_rows:
        lines.extend(["", "Sample selected rows:"])
        for row in selected_rows[:5]:
            lines.append(
                "- "
                f"row_id={row.row_id}; review_id={row.review_id}; "
                f"result_version={row.result_version}; form={row.form_id}@{row.form_version}; "
                f"claim_number={row.claim_number}; batch_id={row.batch_id}; outcome={row.outcome}"
            )
        if len(selected_rows) > 5:
            lines.append(f"- ... {len(selected_rows) - 5} more selected row(s)")
    else:
        lines.extend(
            [
                "",
                "No rows are currently selected. Do not use scope='selected' until "
                "the user selects rows.",
            ]
        )
    return "\n".join(lines)


def _format_foreign_keys(keys: list[ForeignKeyInfo]) -> str:
    if not keys:
        return "No foreign keys found."
    return "\n".join(
        "- "
        f"{key.table}({', '.join(key.constrained_columns)}) -> "
        f"{key.referred_table}({', '.join(key.referred_columns)})"
        for key in keys
    )


def _effective_sql_for_scope(state: TFRChatState, sql: str, scope: SQLScope) -> str:
    prepared = validate_readonly_query(sql)
    if scope == "full":
        return prepared
    selected_rows = _selected_rows(state)
    if not selected_rows:
        raise ValueError("No home table rows are selected for selected-scope SQL.")
    if "selected_home_rows" not in prepared.lower():
        raise ValueError(
            "selected-scope SQL must reference the selected_home_rows CTE. "
            "Use scope='full' when you want the whole database."
        )
    return _prepend_selected_rows_cte(prepared, selected_rows)


def _prepend_selected_rows_cte(sql: str, selected_rows: list[SelectedHomeRowContext]) -> str:
    cte = _selected_rows_cte(selected_rows)
    stripped = sql.lstrip()
    leading = sql[: len(sql) - len(stripped)]
    lower = stripped.lower()
    if lower.startswith("with recursive"):
        return f"{leading}WITH RECURSIVE {cte}, {stripped[len('with recursive') :].lstrip()}"
    if lower.startswith("with"):
        return f"{leading}WITH {cte}, {stripped[len('with') :].lstrip()}"
    return f"{leading}WITH {cte}\n{stripped}"


def _selected_rows_cte(selected_rows: list[SelectedHomeRowContext]) -> str:
    columns = _selected_rows_columns()
    values = [
        "("
        + ", ".join(
            [
                _sql_literal(row.row_id),
                _sql_literal(row.review_id),
                _sql_literal(row.result_version),
                _sql_literal(row.form_id),
                _sql_literal(row.form_version),
                _sql_literal(row.form_key),
                _sql_literal(row.claim_number),
                _sql_literal(row.batch_id),
                _sql_literal(row.run_name),
                _sql_literal(row.source),
                _sql_literal(row.outcome),
                _sql_literal(row.title),
                _sql_literal(row.created_at),
                _sql_literal(row.updated_at),
                str(row.question_count),
                str(row.no_count),
                str(row.driver_count),
                "1" if row.edited else "0",
            ]
        )
        + ")"
        for row in selected_rows
    ]
    return f"selected_home_rows({', '.join(columns)}) AS (VALUES {', '.join(values)})"


def _selected_rows_columns() -> list[str]:
    return [
        "row_id",
        "review_id",
        "result_version",
        "form_id",
        "form_version",
        "form_key",
        "claim_number",
        "batch_id",
        "run_name",
        "source",
        "outcome",
        "title",
        "created_at",
        "updated_at",
        "question_count",
        "no_count",
        "driver_count",
        "edited",
    ]


def _sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _append_query_components(state: TFRChatState, result: QueryResult) -> None:
    state.components.append(
        generate_data_table(
            headers=result.columns,
            rows=result.rows,
            caption=_result_caption(result),
            sortable=True,
        )
    )


def _result_caption(result: QueryResult) -> str:
    suffix = " (truncated)" if result.truncated else ""
    return f"SQL result: {result.row_count} row(s){suffix}"


def _result_status(
    result: QueryResult,
    *,
    table_rendered: bool,
    dataset_handle: str | None = None,
) -> str:
    handle_suffix = f"; saved dataset handle {dataset_handle}" if dataset_handle else ""
    if table_rendered:
        if result.truncated:
            return f"SQL query complete; rendered first {result.row_count} row(s){handle_suffix}."
        return f"SQL query complete; rendered {result.row_count} row(s){handle_suffix}."
    return f"SQL query complete; previewed {result.returned_row_count} row(s){handle_suffix}."


def _format_query_result_for_agent(
    result: QueryResult,
    *,
    table_rendered: bool,
    dataset_handle: str | None = None,
) -> str:
    payload = {
        "columns": result.columns,
        "preview_rows": result.agent_rows,
        "preview_row_count": result.returned_row_count,
        "rendered_row_count": result.row_count,
        "table_rendered": table_rendered,
        "persisted": dataset_handle is not None,
        "dataset_handle": dataset_handle,
        "truncated": result.truncated,
        "scope": result.scope,
    }
    table_note = (
        "A result table was emitted to the chat UI."
        if table_rendered
        else "No result table was emitted; ask the user if they want the table shown."
    )
    return (
        "SQL query executed successfully. "
        + table_note
        + "\nPreview for reasoning:\n"
        + json.dumps(payload, ensure_ascii=False, indent=2)
    )


def _format_sql_error_for_agent(
    operation: Literal["execute", "explain"],
    error: SQLSafetyError | ValueError | SQLDatabaseError,
    *,
    sql: str,
) -> str:
    problem = str(error)
    payload = {
        "operation": operation,
        "error_type": error.__class__.__name__,
        "message": problem,
        "sql": error.sql if isinstance(error, SQLDatabaseError) and error.sql else sql,
        "hint": _sql_error_hint(error),
    }
    return (
        f"Unable to {operation} SQL. The tool caught the database error so you can "
        "revise the query and try again.\n" + json.dumps(payload, ensure_ascii=False, indent=2)
    )


def _sql_error_status(
    operation: Literal["execute", "explain"],
    error: SQLSafetyError | ValueError | SQLDatabaseError,
) -> str:
    if isinstance(error, SQLDatabaseError):
        return f"SQL {operation} failed: {error.message}"
    return f"SQL {operation} blocked: {error}"


def _sql_error_hint(error: SQLSafetyError | ValueError | SQLDatabaseError) -> str:
    message = str(error).lower()
    if isinstance(error, SQLSafetyError):
        return "Use a single read-only SELECT or WITH query."
    if "selected_home_rows" in message:
        return (
            "Call get_selected_rows_info, then include selected_home_rows in the "
            "selected-scope query."
        )
    if "no such table" in message or "does not exist" in message:
        return "Call get_tables or get_schema to verify the table name before retrying."
    if "no such column" in message or "unknown column" in message:
        return "Call get_table_info for the tables involved and correct the column or alias."
    if "syntax" in message:
        return "Check the active dialect instructions and rewrite the SQL syntax."
    return "Inspect schema context, adjust the SQL, and retry with a narrow LIMIT when useful."
