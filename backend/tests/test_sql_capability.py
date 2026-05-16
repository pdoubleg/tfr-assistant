import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.capabilities.sql.backend import SQLDatabaseError, SQLiteDatabase, create_sql_database
from app.capabilities.sql.capability import (
    _effective_sql_for_scope,
    _format_query_result_for_agent,
    _format_selected_rows_info,
    _format_sql_error_for_agent,
)
from app.capabilities.sql.safety import SQLSafetyError, validate_readonly_query
from app.capabilities.sql.types import QueryResult
from app.models.chat_state import ChatRunContext, SelectedHomeRowContext, TFRChatState


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def test_validate_readonly_query_allows_selects() -> None:
    assert validate_readonly_query("select * from audit_reviews") == "select * from audit_reviews"


def test_validate_readonly_query_rejects_multi_statement_write() -> None:
    with pytest.raises(SQLSafetyError, match="Multiple SQL statements"):
        validate_readonly_query("select * from audit_reviews; drop table audit_reviews")


def test_selected_scope_requires_selected_home_rows_reference() -> None:
    state = TFRChatState(
        run_context=ChatRunContext(
            selected_home_rows=[
                SelectedHomeRowContext(
                    row_id="review-1:current",
                    review_id="review-1",
                    result_version="current",
                )
            ]
        )
    )

    with pytest.raises(ValueError, match="selected_home_rows"):
        _effective_sql_for_scope(state, "select * from audit_reviews", "selected")

    scoped_sql = _effective_sql_for_scope(
        state,
        "select audit_reviews.id from audit_reviews "
        "join selected_home_rows on selected_home_rows.review_id = audit_reviews.id",
        "selected",
    )
    assert scoped_sql.startswith("WITH selected_home_rows")
    assert "VALUES ('review-1:current', 'review-1'" in scoped_sql


@pytest.mark.anyio
async def test_database_execute_limits_agent_rows() -> None:
    local_engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with local_engine.begin() as connection:
            await connection.execute(text("create table sample (id integer, name text)"))
            await connection.execute(
                text("insert into sample (id, name) values (1, 'alpha'), (2, 'beta')")
            )

        database = SQLiteDatabase(local_engine, max_display_rows=10, max_agent_rows=5)
        result = await database.execute("select id, name from sample order by id", agent_limit=1)

        assert result.columns == ["id", "name"]
        assert result.row_count == 2
        assert result.returned_row_count == 1
        assert result.agent_rows == [{"id": 1, "name": "alpha"}]
    finally:
        await local_engine.dispose()


@pytest.mark.anyio
async def test_database_execute_wraps_driver_errors_for_tool_handling() -> None:
    local_engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with local_engine.begin() as connection:
            await connection.execute(text("create table sample (id integer, name text)"))

        database = SQLiteDatabase(local_engine)
        with pytest.raises(SQLDatabaseError) as exc_info:
            await database.execute("select missing_column from sample")

        error = exc_info.value
        assert error.operation == "execute"
        assert error.dialect_name == "sqlite"
        assert error.sql == "select missing_column from sample"
        assert "missing_column" in error.message
    finally:
        await local_engine.dispose()


@pytest.mark.anyio
async def test_database_factory_selects_sqlite_backend() -> None:
    local_engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        database = create_sql_database(local_engine)
        assert isinstance(database, SQLiteDatabase)
        assert "SQLite syntax" in database.prompt_instructions
    finally:
        await local_engine.dispose()


def test_query_result_message_mentions_when_table_is_not_rendered() -> None:
    result = QueryResult(
        sql="select 1 as value",
        columns=["value"],
        rows=[[1]],
        agent_rows=[{"value": 1}],
        row_count=1,
        returned_row_count=1,
        truncated=False,
        agent_limit=10,
        scope="full",
    )

    message = _format_query_result_for_agent(result, table_rendered=False)

    assert "No result table was emitted" in message
    assert '"table_rendered": false' in message


def test_sql_error_message_is_structured_for_agent_retry() -> None:
    error = SQLDatabaseError(
        "execute",
        "sqlite",
        "no such column: missing_column",
        sql="select missing_column from sample",
    )

    message = _format_sql_error_for_agent("execute", error, sql="select missing_column from sample")

    assert "Unable to execute SQL" in message
    assert '"error_type": "SQLDatabaseError"' in message
    assert '"message": "no such column: missing_column"' in message
    assert "Call get_table_info" in message


def test_selected_rows_info_explains_join_recipe() -> None:
    selected_rows = [
        SelectedHomeRowContext(
            row_id="review-1:current",
            review_id="review-1",
            result_version="current",
            form_id="tfr_default",
            form_version="v0.1",
            claim_number="claim-123",
            batch_id="batch-1",
            outcome="Meets",
        )
    ]

    info = _format_selected_rows_info(selected_rows)

    assert "Currently selected rows: 1" in info
    assert "selected_home_rows.review_id = audit_reviews.id" in info
    assert "FROM selected_home_rows shr" in info
    assert "review_id=review-1" in info
