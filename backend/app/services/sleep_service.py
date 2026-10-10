"""
==============================================================================
Module Name:   sleep_service.py
Description:   Source module sleep_service.py.
Author:        Mai Tan Duc <ducmai.network@gmail.com>
Created:       2026-10-10
Version:       1.0.0
License:       MIT
==============================================================================
Usage:         python3 sleep_service.py [options]
Notes:         Requires Python 3.8+
==============================================================================
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import aiosqlite

from app.database import outages_repo

logger = logging.getLogger("internet_monitor.sleep")

_last_tick_wall: datetime | None = None


async def check_gap(conn: aiosqlite.Connection, threshold_seconds: float) -> None:
    global _last_tick_wall
    now = datetime.now(timezone.utc)

    if _last_tick_wall is not None:
        gap_seconds = (now - _last_tick_wall).total_seconds()
        if gap_seconds > threshold_seconds:
            await outages_repo.insert_sleep_gap(conn, started_at=_last_tick_wall, ended_at=now)
            logger.info(
                "Detected a %.0fs gap since the last check (threshold %.0fs) - "
                "recorded as system_sleep, excluded from downtime.",
                gap_seconds,
                threshold_seconds,
            )

    _last_tick_wall = now


def reset_state() -> None:
    """Used by tests."""
    global _last_tick_wall
    _last_tick_wall = None
