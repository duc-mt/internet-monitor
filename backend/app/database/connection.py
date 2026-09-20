"""
Thin wrapper around a single shared aiosqlite connection.

SQLite handles one writer at a time regardless of how many connections you
open, and WAL mode lets readers proceed concurrently with a writer. For an
app with this write volume (one row per check, a handful of checks per
second at most) a single shared connection guarded by an asyncio.Lock for
writes is simpler and just as fast as a connection pool, and avoids
"database is locked" errors that a naive multi-connection setup would hit.
"""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

import aiosqlite

from app.config import DATABASE_PATH, ensure_data_dir

logger = logging.getLogger("internet_monitor.database")

_SCHEMA_PATH = Path(__file__).parent / "schema.sql"

_connection: aiosqlite.Connection | None = None
_write_lock = asyncio.Lock()


async def init_db(db_path: Path | None = None) -> aiosqlite.Connection:
    """Open the database (creating the file/dir if needed) and apply the schema."""
    global _connection
    ensure_data_dir()
    path = db_path or DATABASE_PATH
    conn = await aiosqlite.connect(str(path))
    conn.row_factory = aiosqlite.Row
    await conn.execute("PRAGMA foreign_keys = ON")
    schema_sql = _SCHEMA_PATH.read_text()
    await conn.executescript(schema_sql)
    await conn.commit()
    _connection = conn
    logger.info("Database ready at %s", path)
    return conn


async def close_db() -> None:
    global _connection
    if _connection is not None:
        await _connection.close()
        _connection = None


def get_connection() -> aiosqlite.Connection:
    if _connection is None:
        raise RuntimeError("Database has not been initialized yet (call init_db() first)")
    return _connection


@asynccontextmanager
async def write_transaction() -> AsyncIterator[aiosqlite.Connection]:
    """Serialize writes and commit/rollback as a unit."""
    conn = get_connection()
    async with _write_lock:
        try:
            yield conn
            await conn.commit()
        except Exception:
            await conn.rollback()
            raise


# FastAPI dependency
async def get_db() -> AsyncIterator[aiosqlite.Connection]:
    yield get_connection()
