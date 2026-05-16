"""Read-only SQL validation helpers."""

from __future__ import annotations

import re


class SQLSafetyError(ValueError):
    """Raised when a SQL statement is not safe for agent execution."""


FORBIDDEN_KEYWORDS = {
    "ALTER",
    "ANALYZE",
    "ATTACH",
    "CALL",
    "COPY",
    "CREATE",
    "DELETE",
    "DETACH",
    "DO",
    "DROP",
    "GRANT",
    "INSERT",
    "MERGE",
    "REINDEX",
    "REPLACE",
    "REVOKE",
    "TRUNCATE",
    "UPDATE",
    "VACUUM",
}

ALLOWED_FIRST_KEYWORDS = {"SELECT", "WITH"}


def _mask_comments_and_literals(sql: str) -> str:
    """Remove SQL comments and mask quoted strings/identifiers for keyword scanning."""

    output: list[str] = []
    index = 0
    quote: str | None = None
    line_comment = False
    block_comment = False

    while index < len(sql):
        char = sql[index]
        next_char = sql[index + 1] if index + 1 < len(sql) else ""

        if line_comment:
            if char in "\r\n":
                line_comment = False
                output.append(char)
            else:
                output.append(" ")
            index += 1
            continue

        if block_comment:
            if char == "*" and next_char == "/":
                output.extend("  ")
                block_comment = False
                index += 2
            else:
                output.append(" ")
                index += 1
            continue

        if quote:
            if char == quote:
                if next_char == quote:
                    output.extend("  ")
                    index += 2
                    continue
                quote = None
            output.append(" ")
            index += 1
            continue

        if char == "-" and next_char == "-":
            output.extend("  ")
            line_comment = True
            index += 2
            continue

        if char == "/" and next_char == "*":
            output.extend("  ")
            block_comment = True
            index += 2
            continue

        if char in {"'", '"'}:
            quote = char
            output.append(" ")
            index += 1
            continue

        output.append(char)
        index += 1

    return "".join(output)


def validate_readonly_query(sql: str) -> str:
    """Validate a model-proposed query before it touches the app database."""

    prepared = sql.strip()
    if not prepared:
        raise SQLSafetyError("SQL query is empty.")

    masked = _mask_comments_and_literals(prepared)
    if ";" in masked.strip().rstrip(";"):
        raise SQLSafetyError("Multiple SQL statements are not allowed.")

    tokens = re.findall(r"[A-Za-z_][A-Za-z0-9_]*", masked.upper())
    if not tokens:
        raise SQLSafetyError("SQL query did not contain a recognized statement.")

    first_keyword = tokens[0]
    if first_keyword not in ALLOWED_FIRST_KEYWORDS:
        allowed = ", ".join(sorted(ALLOWED_FIRST_KEYWORDS))
        raise SQLSafetyError(f"Only read-only {allowed} queries are allowed.")

    forbidden = sorted(FORBIDDEN_KEYWORDS.intersection(tokens))
    if forbidden:
        raise SQLSafetyError(
            "Write or administrative SQL is blocked in chat tools: " + ", ".join(forbidden) + "."
        )

    return prepared
