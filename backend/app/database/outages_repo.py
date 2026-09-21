from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

import aiosqlite

from app.database.connection import write_transaction
from app.models.outage import OutageOut


def _row_to_outage(row: aiosqlite.Row) -> OutageOut:
    return OutageOut(
        id=row["id"],
        started_at=row["started_at"],
        ended_at=row["ended_at"],
        duration_seconds=row["duration_seconds"],
        reason=row["reason"],
        affected_targets=json.loads(row["affected_targets"] or "[]"),
        failed_checks=row["failed_checks"],
        is_active=row["ended_at"] is None,
    )


async def get_active_outage(conn: aiosqlite.Connection) -> Optional[OutageOut]:
    async with conn.execute(
        "SELECT * FROM outages WHERE ended_at IS NULL ORDER BY started_at DESC LIMIT 1"
    ) as cursor:
        row = await cursor.fetchone()
    return _row_to_outage(row) if row else None


async def start_outage(
    conn: aiosqlite.Connection, *, reason: str, affected_targets: list[str], failed_checks: int
) -> OutageOut:
    started_at = datetime.now(timezone.utc).isoformat()
    async with write_transaction() as tx:
        cursor = await tx.execute(
            """
            INSERT INTO outages (started_at, reason, affected_targets, failed_checks)
            VALUES (?, ?, ?, ?)
            """,
            (started_at, reason, json.dumps(affected_targets), failed_checks),
        )
        outage_id = cursor.lastrowid
    async with conn.execute("SELECT * FROM outages WHERE id = ?", (outage_id,)) as cursor:
        row = await cursor.fetchone()
    return _row_to_outage(row)


async def insert_sleep_gap(conn: aiosqlite.Connection, *, started_at: datetime, ended_at: datetime) -> OutageOut:
    """
    Records a detected system-sleep gap as a *closed* outage-shaped row
    (both timestamps set immediately - there's no "active" state for this,
    since by the time we detect it, it has already ended). Kept in the same
    `outages` table rather than a separate one so the Outages page can show
    everything on one timeline; `reason='system_sleep'` is what excludes it
    from downtime/uptime% (see statistics_service) and from the "real
    outage" active-outage singleton logic (which only ever looks at rows
    with ended_at IS NULL - this row never is).
    """
    duration = (ended_at - started_at).total_seconds()
    async with write_transaction() as tx:
        cursor = await tx.execute(
            """
            INSERT INTO outages (started_at, ended_at, duration_seconds, reason, affected_targets, failed_checks)
            VALUES (?, ?, ?, 'system_sleep', '[]', 0)
            """,
            (started_at.isoformat(), ended_at.isoformat(), duration),
        )
        outage_id = cursor.lastrowid
    async with conn.execute("SELECT * FROM outages WHERE id = ?", (outage_id,)) as cursor:
        row = await cursor.fetchone()
    return _row_to_outage(row)


async def end_active_outage(conn: aiosqlite.Connection) -> Optional[OutageOut]:
    active = await get_active_outage(conn)
    if active is None:
        return None
    ended_at = datetime.now(timezone.utc)
    started_at = datetime.fromisoformat(active.started_at)
    duration = (ended_at - started_at).total_seconds()
    async with write_transaction() as tx:
        await tx.execute(
            "UPDATE outages SET ended_at = ?, duration_seconds = ? WHERE id = ?",
            (ended_at.isoformat(), duration, active.id),
        )
    async with conn.execute("SELECT * FROM outages WHERE id = ?", (active.id,)) as cursor:
        row = await cursor.fetchone()
    return _row_to_outage(row)


async def list_outages(
    conn: aiosqlite.Connection, *, start: Optional[str] = None, end: Optional[str] = None, limit: int = 200
) -> list[OutageOut]:
    query = "SELECT * FROM outages WHERE 1=1"
    params: list = []
    if start is not None:
        query += " AND started_at >= ?"
        params.append(start)
    if end is not None:
        query += " AND started_at <= ?"
        params.append(end)
    query += " ORDER BY started_at DESC LIMIT ?"
    params.append(limit)
    async with conn.execute(query, params) as cursor:
        rows = await cursor.fetchall()
    return [_row_to_outage(r) for r in rows]


async def downtime_and_sleep_seconds_in_range(
    conn: aiosqlite.Connection, *, start: str, end: str
) -> tuple[float, float]:
    """
    Returns (real_downtime_seconds, sleep_seconds): the total time within
    [start, end] covered by outage rows, split by whether each row is a
    real outage or a detected system_sleep gap - computed as actual overlap
    with the window, not raw duration_seconds, so an outage that started
    before `start` or is still active past `end` is only counted for the
    portion that actually falls inside the window.
    """
    query = "SELECT started_at, ended_at, reason FROM outages WHERE started_at < ? AND (ended_at IS NULL OR ended_at > ?)"
    async with conn.execute(query, (end, start)) as cursor:
        rows = await cursor.fetchall()

    range_start = datetime.fromisoformat(start)
    range_end = datetime.fromisoformat(end)
    now = datetime.now(timezone.utc)

    real_downtime = 0.0
    sleep_seconds = 0.0
    for row in rows:
        o_start = datetime.fromisoformat(row["started_at"])
        o_end = datetime.fromisoformat(row["ended_at"]) if row["ended_at"] else now
        overlap = max(0.0, (min(o_end, range_end) - max(o_start, range_start)).total_seconds())
        if row["reason"] == "system_sleep":
            sleep_seconds += overlap
        else:
            real_downtime += overlap
    return real_downtime, sleep_seconds


async def outage_stats_in_range(conn: aiosqlite.Connection, *, start: str, end: str) -> dict:
    # reason != 'system_sleep' - a detected sleep gap must not inflate the
    # "N outages, longest X" summary the same way it must not count as
    # downtime; see downtime_and_sleep_seconds_in_range above.
    async with conn.execute(
        """
        SELECT COUNT(*) AS outage_count, MAX(duration_seconds) AS longest
        FROM outages
        WHERE started_at BETWEEN ? AND ? AND ended_at IS NOT NULL AND reason != 'system_sleep'
        """,
        (start, end),
    ) as cursor:
        row = await cursor.fetchone()
    return dict(row) if row else {"outage_count": 0, "longest": None}
