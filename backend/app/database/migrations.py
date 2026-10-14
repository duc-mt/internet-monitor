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

import json

import aiosqlite

# (table, column, SQL type) - each is added only if not already present.
# Append here when a future change needs a new column on an existing table.
_ADDITIVE_COLUMNS: list[tuple[str, str, str]] = [
    ("measurements", "network_name", "TEXT"),
    # Burst Probing summary statistics (NULL on rows written before the upgrade)
    ("measurements", "median_ms", "REAL"),
    ("measurements", "p25_ms", "REAL"),
    ("measurements", "p75_ms", "REAL"),
    ("measurements", "p95_ms", "REAL"),
    ("measurements", "min_ms", "REAL"),
    ("measurements", "max_ms", "REAL"),
    ("measurements", "iqr_ms", "REAL"),
    ("measurements", "jitter_rfc3550", "REAL"),
    ("measurements", "packet_count", "INTEGER"),
]


# PRAGMA user_version after the last data migration below has run.
SCHEMA_VERSION = 2

_LEGACY_TARGET_INTERVAL_SECONDS = 5  # the pre-Burst-Probing default
_BURST_TARGET_INTERVAL_SECONDS = 60
_LEGACY_RETENTION_DAYS = 30  # the pre-tiered-storage default
_TIERED_RETENTION_DAYS = 90


async def run_migrations(conn: aiosqlite.Connection) -> None:
    changed = False
    for table, column, col_type in _ADDITIVE_COLUMNS:
        if not await _column_exists(conn, table, column):
            await conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
            changed = True

    version = await _user_version(conn)
    if version < 2:
        await _migrate_to_burst_probing_defaults(conn)
        changed = True
    if version < SCHEMA_VERSION:
        await conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        changed = True
    if changed:
        await conn.commit()


async def _migrate_to_burst_probing_defaults(conn: aiosqlite.Connection) -> None:
    """
    v2: the old 5-second "ping a few times" default makes no sense for Burst
    Probing - one 15-probe burst every 5 s is 17k rows/day per target, an order
    of magnitude past the storage budget. Targets and stored settings still on
    the old *defaults* move to the new ones; anything a user set to another
    value is left alone.
    """
    await conn.execute(
        "UPDATE targets SET interval_seconds = ? WHERE interval_seconds = ?",
        (_BURST_TARGET_INTERVAL_SECONDS, _LEGACY_TARGET_INTERVAL_SECONDS),
    )
    async with conn.execute("SELECT value FROM settings WHERE key = 'app_settings'") as cursor:
        row = await cursor.fetchone()
    if row is None:
        return
    try:
        stored = json.loads(row["value"])
    except ValueError:
        return
    if stored.get("default_target_interval_seconds") == _LEGACY_TARGET_INTERVAL_SECONDS:
        stored["default_target_interval_seconds"] = _BURST_TARGET_INTERVAL_SECONDS
    if stored.get("data_retention_days") == _LEGACY_RETENTION_DAYS:
        stored["data_retention_days"] = _TIERED_RETENTION_DAYS
    stored.pop("pings_per_check", None)  # superseded by burst_packet_count
    await conn.execute("UPDATE settings SET value = ? WHERE key = 'app_settings'", (json.dumps(stored),))


async def _user_version(conn: aiosqlite.Connection) -> int:
    async with conn.execute("PRAGMA user_version") as cursor:
        row = await cursor.fetchone()
    return int(row[0]) if row else 0


async def _column_exists(conn: aiosqlite.Connection, table: str, column: str) -> bool:
    async with conn.execute(f"PRAGMA table_info({table})") as cursor:
        rows = await cursor.fetchall()
    return any(row["name"] == column for row in rows)
