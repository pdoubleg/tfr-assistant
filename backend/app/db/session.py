from collections.abc import AsyncIterator

from sqlalchemy import event
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings
from app.db.models import Base

settings = get_settings()
settings.data_dir.mkdir(parents=True, exist_ok=True)


def get_backend_name(database_url: str) -> str:
    return make_url(database_url).get_backend_name()


def is_sqlite_url(database_url: str) -> bool:
    return get_backend_name(database_url) == "sqlite"


def is_postgres_url(database_url: str) -> bool:
    return get_backend_name(database_url) == "postgresql"


def create_app_engine(database_url: str) -> AsyncEngine:
    engine_kwargs: dict[str, object] = {
        "future": True,
        "pool_pre_ping": True,
    }

    if is_sqlite_url(database_url):
        engine_kwargs.pop("pool_pre_ping", None)
    elif is_postgres_url(database_url):
        engine_kwargs.update(
            {
                "pool_size": 5,
                "max_overflow": 10,
                "pool_timeout": 30,
                "pool_recycle": 1800,
            }
        )

    return create_async_engine(database_url, **engine_kwargs)


engine = create_app_engine(settings.database_url)
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    expire_on_commit=False,
    autoflush=False,
)


if is_sqlite_url(settings.database_url):

    @event.listens_for(engine.sync_engine, "connect")
    def set_sqlite_pragmas(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()


async def init_db() -> None:
    """Create missing tables for local/dev/test bootstrap only.

    Alembic migrations are the source of truth for persistent dev and production
    schema changes. Do not add production migrations here.
    """

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)


async def get_session() -> AsyncIterator[AsyncSession]:
    async with AsyncSessionLocal() as session:
        yield session
