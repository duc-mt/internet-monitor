"""
==============================================================================
Module Name:   settings_repo.py
Description:   Source module settings_repo.py.
Author:        Mai Tan Duc <ducmai.network@gmail.com>
Created:       2026-10-10
Version:       1.0.0
License:       MIT
==============================================================================
Usage:         python3 settings_repo.py [options]
Notes:         Requires Python 3.8+
==============================================================================
"""

from __future__ import annotations

import json

import aiosqlite

from app.database.connection import write_transaction

_SETTINGS_KEY = "app_settings"


async def load_raw_settings(conn: aiosqlite.Connection) -> dict | None:
    async with conn.execute("SELECT value FROM settings WHERE key = ?", (_SETTINGS_KEY,)) as cursor:
        row = await cursor.fetchone()
    if row is None:
        return None
    return json.loads(row["value"])


async def save_raw_settings(conn: aiosqlite.Connection, data: dict) -> None:
    payload = json.dumps(data)
    async with write_transaction() as tx:
        await tx.execute(
            """
            INSERT INTO settings (key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (_SETTINGS_KEY, payload),
        )
