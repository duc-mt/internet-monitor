"""
Lightweight, additive-only schema migrations for databases created by an
earlier version of the app.

New tables belong directly in schema.sql (`CREATE TABLE IF NOT EXISTS`
already handles those safely for both fresh and existing databases). This
module exists only to add a *column* to a table that may already exist from
before that column was introduced - `CREATE TABLE IF NOT EXISTS` does not
retroactively widen an existing table, so a plain schema.sql change alone
would silently no-op on an upgrade and the app would crash the first time it
tried to read/write the new column.
"""

from __future__ import annotations

import aiosqlite

# (table, column, SQL type) - each is added only if not already present.
# Append here when a future change needs a new column on an existing table.
_ADDITIVE_COLUMNS: list[tuple[str, str, str]] = [
    ("measurements", "network_name", "TEXT"),
]


async def run_migrations(conn: aiosqlite.Connection) -> None:
    changed = False
    for table, column, col_type in _ADDITIVE_COLUMNS:
        if not await _column_exists(conn, table, column):
            await conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
            changed = True
    if changed:
        await conn.commit()


async def _column_exists(conn: aiosqlite.Connection, table: str, column: str) -> bool:
    async with conn.execute(f"PRAGMA table_info({table})") as cursor:
        rows = await cursor.fetchall()
    return any(row["name"] == column for row in rows)
