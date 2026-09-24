from __future__ import annotations

from datetime import datetime, timedelta, timezone

import aiosqlite

from app.database.connection import write_transaction
from app.models.measurement import MeasurementCreate, MeasurementOut


def _row_to_measurement(row: aiosqlite.Row) -> MeasurementOut:
    return MeasurementOut(
        id=row["id"],
        target_id=row["target_id"],
        target_name=row["name"] if "name" in row.keys() else None,
        timestamp=row["timestamp"],
        latency_ms=row["latency_ms"],
        packet_loss=row["packet_loss"],
        jitter_ms=row["jitter_ms"],
        success=bool(row["success"]),
        error=row["error"],
        network_name=row["network_name"] if "network_name" in row.keys() else None,
    )


async def insert_measurement(conn: aiosqlite.Connection, data: MeasurementCreate) -> int:
    async with write_transaction() as tx:
        cursor = await tx.execute(
            """
            INSERT INTO measurements (target_id, timestamp, latency_ms, packet_loss, jitter_ms, success, error, network_name)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                data.target_id,
                data.timestamp,
                data.latency_ms,
                data.packet_loss,
                data.jitter_ms,
                int(data.success),
                data.error,
                data.network_name,
            ),
        )
    return int(cursor.lastrowid or 0)


async def list_measurements(
    conn: aiosqlite.Connection,
    *,
    target_id: int | None = None,
    start: str | None = None,
    end: str | None = None,
    limit: int = 1000,
) -> list[MeasurementOut]:
    query = "SELECT m.*, t.name FROM measurements m JOIN targets t ON t.id = m.target_id WHERE 1=1"
    params: list = []
    if target_id is not None:
        query += " AND m.target_id = ?"
        params.append(target_id)
    if start is not None:
        query += " AND m.timestamp >= ?"
        params.append(start)
    if end is not None:
        query += " AND m.timestamp <= ?"
        params.append(end)
    query += " ORDER BY m.timestamp DESC LIMIT ?"
    params.append(limit)
    async with conn.execute(query, params) as cursor:
        rows = await cursor.fetchall()
    return [_row_to_measurement(r) for r in rows]


async def latest_measurement(conn: aiosqlite.Connection, target_id: int) -> MeasurementOut | None:
    async with conn.execute(
        "SELECT m.*, t.name FROM measurements m JOIN targets t ON t.id = m.target_id "
        "WHERE m.target_id = ? ORDER BY m.timestamp DESC LIMIT 1",
        (target_id,),
    ) as cursor:
        row = await cursor.fetchone()
    return _row_to_measurement(row) if row else None


async def latest_measurements_all(conn: aiosqlite.Connection) -> list[MeasurementOut]:
    """Most recent measurement per enabled target - used for the live status view."""
    query = """
        SELECT m.*, t.name FROM measurements m
        JOIN targets t ON t.id = m.target_id
        WHERE m.id IN (
            SELECT MAX(id) FROM measurements GROUP BY target_id
        )
        AND t.enabled = 1
    """
    async with conn.execute(query) as cursor:
        rows = await cursor.fetchall()
    return [_row_to_measurement(r) for r in rows]


async def recent_results_for_targets(
    conn: aiosqlite.Connection, target_ids: list[int], count: int
) -> dict[int, list[bool]]:
    """For each target id, the `count` most recent success flags, newest first."""
    results: dict[int, list[bool]] = {}
    for target_id in target_ids:
        async with conn.execute(
            "SELECT success FROM measurements WHERE target_id = ? ORDER BY timestamp DESC LIMIT ?",
            (target_id, count),
        ) as cursor:
            rows = await cursor.fetchall()
        results[target_id] = [bool(r["success"]) for r in rows]
    return results


async def latencies_in_range(conn: aiosqlite.Connection, *, target_id: int | None, start: str, end: str) -> list[float]:
    query = "SELECT latency_ms FROM measurements WHERE timestamp BETWEEN ? AND ? AND latency_ms IS NOT NULL"
    params: list = [start, end]
    if target_id is not None:
        query += " AND target_id = ?"
        params.append(target_id)
    async with conn.execute(query, params) as cursor:
        rows = await cursor.fetchall()
    return [r["latency_ms"] for r in rows]


async def aggregate_in_range(conn: aiosqlite.Connection, *, target_id: int | None, start: str, end: str) -> dict:
    query = """
        SELECT
            COUNT(*) AS sample_count,
            AVG(packet_loss) AS avg_packet_loss,
            AVG(jitter_ms) AS avg_jitter,
            MIN(timestamp) AS first_ts,
            MAX(timestamp) AS last_ts
        FROM measurements
        WHERE timestamp BETWEEN ? AND ?
    """
    params: list = [start, end]
    if target_id is not None:
        query += " AND target_id = ?"
        params.append(target_id)
    async with conn.execute(query, params) as cursor:
        row = await cursor.fetchone()
    return dict(row) if row else {}


async def earliest_timestamp(conn: aiosqlite.Connection) -> str | None:
    async with conn.execute("SELECT MIN(timestamp) AS ts FROM measurements") as cursor:
        row = await cursor.fetchone()
    return row["ts"] if row else None


async def delete_older_than(conn: aiosqlite.Connection, retention_days: int) -> int:
    cutoff = (datetime.now(timezone.utc) - timedelta(days=retention_days)).isoformat()
    async with write_transaction() as tx:
        cursor = await tx.execute("DELETE FROM measurements WHERE timestamp < ?", (cutoff,))
    return cursor.rowcount


async def downsample_older_than(conn: aiosqlite.Connection, days_old: int = 7) -> int:
    """
    Downsamples measurements older than `days_old` into 1-hour buckets to save space.
    Leaves data newer than `days_old` at high resolution (e.g. 5 seconds).
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days_old)).isoformat()

    query = """
        SELECT
            target_id,
            strftime('%Y-%m-%dT%H:00:00Z', timestamp) AS hour_bucket,
            AVG(latency_ms) AS latency_ms,
            AVG(packet_loss) AS packet_loss,
            AVG(jitter_ms) AS jitter_ms,
            MAX(success) AS success,
            MAX(network_name) AS network_name
        FROM measurements
        WHERE timestamp < ?
        GROUP BY target_id, hour_bucket
        HAVING COUNT(*) > 1
    """

    async with write_transaction() as tx:
        async with tx.execute(query, (cutoff,)) as cursor:
            rows = await cursor.fetchall()

        if not rows:
            return 0

        # Delete the fine-grained rows that we are about to replace
        await tx.execute("DELETE FROM measurements WHERE timestamp < ?", (cutoff,))

        # Insert the downsampled hourly rows
        insert_query = """
            INSERT INTO measurements (target_id, timestamp, latency_ms, packet_loss, jitter_ms, success, error, network_name)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """
        insert_data = [
            (
                row["target_id"],
                row["hour_bucket"],
                row["latency_ms"],
                row["packet_loss"],
                row["jitter_ms"],
                row["success"],
                "Downsampled",  # indicate this is an aggregated row
                row["network_name"],
            )
            for row in rows
        ]
        await tx.executemany(insert_query, insert_data)

    return len(insert_data)
