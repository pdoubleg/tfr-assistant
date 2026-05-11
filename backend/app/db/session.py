from collections.abc import AsyncIterator

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.db.models import Base

settings = get_settings()
settings.data_dir.mkdir(parents=True, exist_ok=True)

engine = create_async_engine(settings.database_url, future=True)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


if settings.database_url.startswith("sqlite"):

    @event.listens_for(engine.sync_engine, "connect")
    def set_sqlite_pragmas(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


async def init_db() -> None:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
        if settings.database_url.startswith("sqlite"):
            await connection.run_sync(_run_sqlite_migrations)


def _run_sqlite_migrations(connection) -> None:
    """Apply small additive migrations for local SQLite databases."""

    batch_columns = {
        row[1] for row in connection.exec_driver_sql("PRAGMA table_info(audit_batches)").fetchall()
    }
    additions = {
        "template_id": "ALTER TABLE audit_batches ADD COLUMN template_id VARCHAR(36)",
        "started_at": "ALTER TABLE audit_batches ADD COLUMN started_at DATETIME",
        "completed_at": "ALTER TABLE audit_batches ADD COLUMN completed_at DATETIME",
    }
    for column, statement in additions.items():
        if column not in batch_columns:
            connection.exec_driver_sql(statement)

    eval_run_columns = {
        row[1] for row in connection.exec_driver_sql("PRAGMA table_info(eval_runs)").fetchall()
    }
    eval_run_additions = {
        "lineage_id": "ALTER TABLE eval_runs ADD COLUMN lineage_id VARCHAR(36)",
        "source_run_id": "ALTER TABLE eval_runs ADD COLUMN source_run_id VARCHAR(36)",
        "config_version": "ALTER TABLE eval_runs ADD COLUMN config_version INTEGER DEFAULT 1",
    }
    for column, statement in eval_run_additions.items():
        if column not in eval_run_columns:
            connection.exec_driver_sql(statement)
    if "lineage_id" in eval_run_columns or "lineage_id" in eval_run_additions:
        connection.exec_driver_sql("UPDATE eval_runs SET lineage_id = id WHERE lineage_id IS NULL")


async def get_session() -> AsyncIterator[AsyncSession]:
    async with AsyncSessionLocal() as session:
        yield session
