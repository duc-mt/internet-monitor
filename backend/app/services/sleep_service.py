"""
Distinguishes "the laptop was asleep" from "the internet was actually
down", using a single heuristic: the gap in wall-clock time between one
monitoring tick and the next.

Why this works: when a laptop suspends, the OS freezes the process
entirely - no code runs, including the asyncio event loop the ping
scheduler lives on. Nothing gets recorded *during* a real suspend; there
just isn't a gap in the data, because the process itself wasn't running to
create one, no false "8 hours of failed pings" ever get written. What we
see instead, the moment the process resumes, is simply that "now" has
jumped forward far more than one interval's worth of time since the last
tick. A real internet outage, by contrast, still ticks on schedule the
whole time (the process keeps running, checks keep firing every interval,
they just keep failing) - so it does not produce this kind of gap at all.

This is intentionally a single, simple, OS-agnostic signal - no macOS
IOKit power notifications, no Linux D-Bus login1 signals, no Windows power
events - it costs nothing extra to check and needs no platform-specific
code, at the cost of not catching the rarer case where the OS keeps the
process running but tears down networking during sleep (e.g. some laptops'
"Power Nap"/lid-close behavior). See README for that trade-off.

This must only ever be called from *one place at a time* process-wide
(the caller in scheduler.py does this via MonitoringManager._eval_lock),
since multiple concurrent target loops calling it independently would each
detect - and each try to record - the same gap.
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
