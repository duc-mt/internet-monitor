"""
==============================================================================
Module Name:   migrations.py
Description:   Source module migrations.py.
Author:        Mai Tan Duc <ducmai.network@gmail.com>
Created:       2026-10-10
Version:       1.0.0
License:       MIT
==============================================================================
Usage:         python3 migrations.py [options]
Notes:         Requires Python 3.8+
==============================================================================
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
