import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.db.session import repair_local_sqlite_schema


@pytest.mark.anyio
async def test_repair_local_sqlite_schema_adds_missing_eval_metrics_column() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    CREATE TABLE eval_runs (
                        id VARCHAR NOT NULL,
                        name VARCHAR NOT NULL,
                        PRIMARY KEY (id)
                    )
                    """
                )
            )

            await repair_local_sqlite_schema(connection)

            columns = {
                row[1]
                for row in (await connection.execute(text("PRAGMA table_info(eval_runs)"))).all()
            }
            assert "metrics_json" in columns
    finally:
        await engine.dispose()


@pytest.mark.anyio
async def test_repair_local_sqlite_schema_adds_missing_eval_case_metadata_column() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    CREATE TABLE eval_cases (
                        id VARCHAR NOT NULL,
                        dataset_id VARCHAR NOT NULL,
                        claim_number VARCHAR NOT NULL,
                        PRIMARY KEY (id)
                    )
                    """
                )
            )

            await repair_local_sqlite_schema(connection)

            columns = {
                row[1]
                for row in (await connection.execute(text("PRAGMA table_info(eval_cases)"))).all()
            }
            assert "metadata_json" in columns
    finally:
        await engine.dispose()
