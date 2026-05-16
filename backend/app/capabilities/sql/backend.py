"""SQLAlchemy-backed database inspection and query execution."""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Protocol

from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.capabilities.sql.safety import validate_readonly_query
from app.capabilities.sql.types import (
    ColumnInfo,
    ForeignKeyInfo,
    IndexInfo,
    QueryResult,
    SchemaInfo,
    TableInfo,
)


class SQLDatabase(Protocol):
    """Database backend contract used by the SQL capability."""

    @property
    def dialect_name(self) -> str: ...

    @property
    def prompt_instructions(self) -> str: ...

    async def get_tables(self) -> list[str]: ...

    async def get_table_info(self, table_name: str) -> TableInfo | None: ...

    async def get_schema(self) -> SchemaInfo: ...

    async def get_foreign_keys(self, table_name: str) -> list[ForeignKeyInfo]: ...

    async def get_related_tables(self, table_name: str) -> list[ForeignKeyInfo]: ...

    async def explain(self, sql: str) -> str: ...

    async def execute(
        self,
        sql: str,
        *,
        agent_limit: int = 10,
        scope: str = "full",
    ) -> QueryResult: ...


class UnsupportedSQLDialectError(ValueError):
    """Raised when the configured database dialect has no SQL capability backend."""


@dataclass(slots=True)
class SQLAlchemyDatabaseBase(ABC):
    """Shared async SQLAlchemy implementation for database capability backends."""

    engine: AsyncEngine
    max_display_rows: int = 1000
    max_agent_rows: int = 100

    @property
    def dialect_name(self) -> str:
        return self.engine.dialect.name

    @property
    @abstractmethod
    def prompt_instructions(self) -> str:
        """Dialect-specific SQL guidance injected into the agent prompt."""

    async def get_tables(self) -> list[str]:
        async with self.engine.connect() as connection:
            return await connection.run_sync(
                lambda sync_connection: sorted(inspect(sync_connection).get_table_names())
            )

    async def get_table_info(self, table_name: str) -> TableInfo | None:
        async with self.engine.connect() as connection:
            return await connection.run_sync(
                lambda sync_connection: self._inspect_table(sync_connection, table_name)
            )

    async def get_schema(self) -> SchemaInfo:
        table_names = await self.get_tables()
        tables = [
            table
            for table_name in table_names
            if (table := await self.get_table_info(table_name)) is not None
        ]
        return SchemaInfo(tables=tables)

    async def get_foreign_keys(self, table_name: str) -> list[ForeignKeyInfo]:
        table = await self.get_table_info(table_name)
        return table.foreign_keys if table else []

    async def get_related_tables(self, table_name: str) -> list[ForeignKeyInfo]:
        schema = await self.get_schema()
        related: list[ForeignKeyInfo] = []
        for table in schema.tables:
            for foreign_key in table.foreign_keys:
                if table.name == table_name or foreign_key.referred_table == table_name:
                    related.append(foreign_key)
        return related

    async def explain(self, sql: str) -> str:
        prepared = validate_readonly_query(sql)
        explain_sql = self._explain_sql(prepared)
        async with self.engine.connect() as connection:
            result = await connection.execute(text(explain_sql))
            rows = result.fetchall()
        if not rows:
            return "The database returned an empty query plan."
        return "\n".join(" | ".join(_cell_to_text(cell) for cell in row) for row in rows)

    async def execute(
        self,
        sql: str,
        *,
        agent_limit: int = 10,
        scope: str = "full",
    ) -> QueryResult:
        prepared = validate_readonly_query(sql)
        safe_agent_limit = max(1, min(agent_limit, self.max_agent_rows))

        async with self.engine.connect() as connection:
            result = await connection.execute(text(prepared))
            columns = list(result.keys())
            fetched = result.fetchmany(self.max_display_rows + 1)

        truncated = len(fetched) > self.max_display_rows
        rows = fetched[: self.max_display_rows]
        normalized_rows = [[_normalize_cell(cell) for cell in row] for row in rows]
        agent_rows = [
            dict(zip(columns, row, strict=False)) for row in normalized_rows[:safe_agent_limit]
        ]
        return QueryResult(
            sql=prepared,
            columns=columns,
            rows=normalized_rows,
            agent_rows=agent_rows,
            row_count=len(normalized_rows),
            returned_row_count=len(agent_rows),
            truncated=truncated,
            agent_limit=safe_agent_limit,
            scope=scope,
        )

    def _inspect_table(self, sync_connection: Any, table_name: str) -> TableInfo | None:
        inspector = inspect(sync_connection)
        table_names = set(inspector.get_table_names())
        if table_name not in table_names:
            return None

        primary_key = inspector.get_pk_constraint(table_name).get("constrained_columns") or []
        primary_key_set = set(primary_key)
        columns = [
            ColumnInfo(
                name=column["name"],
                type=str(column["type"]),
                nullable=bool(column.get("nullable", True)),
                default=None if column.get("default") is None else str(column.get("default")),
                primary_key=column["name"] in primary_key_set,
            )
            for column in inspector.get_columns(table_name)
        ]
        foreign_keys = [
            ForeignKeyInfo(
                table=table_name,
                constrained_columns=list(foreign_key.get("constrained_columns") or []),
                referred_table=str(foreign_key.get("referred_table") or ""),
                referred_columns=list(foreign_key.get("referred_columns") or []),
                name=foreign_key.get("name"),
            )
            for foreign_key in inspector.get_foreign_keys(table_name)
        ]
        indexes = [
            IndexInfo(
                name=str(index.get("name") or ""),
                columns=list(index.get("column_names") or []),
                unique=bool(index.get("unique")),
            )
            for index in inspector.get_indexes(table_name)
        ]
        return TableInfo(
            name=table_name,
            columns=columns,
            primary_key=list(primary_key),
            foreign_keys=foreign_keys,
            indexes=indexes,
        )

    @abstractmethod
    def _explain_sql(self, prepared: str) -> str:
        """Return dialect-specific EXPLAIN SQL for a validated read-only query."""


@dataclass(slots=True)
class SQLiteDatabase(SQLAlchemyDatabaseBase):
    """SQLite implementation for local TFR databases."""

    @property
    def prompt_instructions(self) -> str:
        return (
            "The active database is SQLite. Use SQLite syntax: LIMIT/OFFSET for row "
            "bounds, json_extract/json_each for JSON fields, strftime/date functions for "
            "dates, and LIKE instead of ILIKE. Boolean-like fields may be stored as 0/1. "
            "The explain tool uses EXPLAIN QUERY PLAN."
        )

    def _explain_sql(self, prepared: str) -> str:
        return f"EXPLAIN QUERY PLAN {prepared}"


@dataclass(slots=True)
class PostgresDatabase(SQLAlchemyDatabaseBase):
    """PostgreSQL implementation for the future production database."""

    @property
    def prompt_instructions(self) -> str:
        return (
            "The active database is PostgreSQL. Use PostgreSQL syntax: LIMIT/OFFSET for "
            "row bounds, ILIKE for case-insensitive matching, date_trunc/extract for date "
            "work, native TRUE/FALSE booleans, and JSON/JSONB operators such as ->, ->>, "
            "and jsonb_array_elements when inspecting JSON columns. The explain tool uses "
            "EXPLAIN (FORMAT TEXT)."
        )

    def _explain_sql(self, prepared: str) -> str:
        return f"EXPLAIN (FORMAT TEXT) {prepared}"


def create_sql_database(
    engine: AsyncEngine,
    *,
    max_display_rows: int = 1000,
    max_agent_rows: int = 100,
) -> SQLDatabase:
    """Create the concrete database backend for the configured SQLAlchemy dialect."""

    dialect_name = engine.dialect.name
    common_kwargs = {
        "engine": engine,
        "max_display_rows": max_display_rows,
        "max_agent_rows": max_agent_rows,
    }
    if dialect_name == "sqlite":
        return SQLiteDatabase(**common_kwargs)
    if dialect_name in _POSTGRES_DIALECTS:
        return PostgresDatabase(**common_kwargs)
    raise UnsupportedSQLDialectError(
        f"SQL database tools do not support the configured dialect '{dialect_name}'."
    )


_POSTGRES_DIALECTS: Sequence[str] = ("postgresql", "postgres")


def _normalize_cell(value: Any) -> str | int | float | bool | None:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, bytes):
        return f"[{len(value)} bytes]"
    if isinstance(value, dict | list | tuple):
        return json.dumps(value, default=str, ensure_ascii=False, separators=(",", ":"))
    return str(value)


def _cell_to_text(value: Any) -> str:
    normalized = _normalize_cell(value)
    return "" if normalized is None else str(normalized)
