"""Typed payloads returned by SQL capability internals."""

from typing import Any

from pydantic import BaseModel, Field


class ColumnInfo(BaseModel):
    name: str
    type: str
    nullable: bool = True
    default: str | None = None
    primary_key: bool = False


class ForeignKeyInfo(BaseModel):
    table: str
    constrained_columns: list[str] = Field(default_factory=list)
    referred_table: str
    referred_columns: list[str] = Field(default_factory=list)
    name: str | None = None


class IndexInfo(BaseModel):
    name: str
    columns: list[str] = Field(default_factory=list)
    unique: bool = False


class TableInfo(BaseModel):
    name: str
    columns: list[ColumnInfo] = Field(default_factory=list)
    primary_key: list[str] = Field(default_factory=list)
    foreign_keys: list[ForeignKeyInfo] = Field(default_factory=list)
    indexes: list[IndexInfo] = Field(default_factory=list)


class SchemaInfo(BaseModel):
    tables: list[TableInfo] = Field(default_factory=list)


class QueryResult(BaseModel):
    sql: str
    columns: list[str]
    rows: list[list[Any]]
    agent_rows: list[dict[str, Any]]
    row_count: int
    returned_row_count: int
    truncated: bool
    agent_limit: int
    scope: str = "full"
