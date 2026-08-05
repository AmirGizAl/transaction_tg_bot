import os
from contextlib import asynccontextmanager

from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from bot.db.models import Base

_engine = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def init_engine(db_path: str) -> None:
    global _engine, _session_factory
    os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
    _engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    _session_factory = async_sessionmaker(_engine, expire_on_commit=False)


def _add_missing_columns(sync_conn) -> None:
    """Lightweight migration: add columns introduced after a table already existed.
    Base.metadata.create_all() only creates missing tables, not missing columns on
    tables that already exist (e.g. an already-deployed production database)."""
    inspector = inspect(sync_conn)
    if "wallets" in inspector.get_table_names():
        columns = {col["name"] for col in inspector.get_columns("wallets")}
        if "deleted_at" not in columns:
            sync_conn.execute(text("ALTER TABLE wallets ADD COLUMN deleted_at DATETIME"))


async def init_db() -> None:
    assert _engine is not None, "call init_engine() first"
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_add_missing_columns)


@asynccontextmanager
async def get_session():
    assert _session_factory is not None, "call init_engine() first"
    async with _session_factory() as session:
        yield session
