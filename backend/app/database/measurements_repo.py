"""
==============================================================================
Module Name:   measurements_repo.py
Description:   Source module measurements_repo.py.
Author:        Mai Tan Duc <ducmai.network@gmail.com>
Created:       2026-10-10
Version:       1.0.0
License:       MIT
==============================================================================
Usage:         python3 measurements_repo.py [options]
Notes:         Requires Python 3.8+
==============================================================================
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import aiosqlite

from app.database.connection import write_transaction
from app.models.measurement import MeasurementCreate, MeasurementOut

# Marker the pre-upgrade downsampler wrote into `error`; kept for rows that
# are served out of the hourly tier so the UI can tell them from raw checks.
DOWNSAMPLED_MARKER = "Downsampled"

_FAR_FUTURE = "9999-12-31T23:59:59+00:00"


def _hour_floor_iso(ts: str) -> str:
    """'2026-10-14T05:12:03.4+00:00' -> '2026-10-14T05:00:00+00:00' (string slice: every timestamp we
    write is ISO-8601 UTC, so the first 13 characters are 'YYYY-MM-DDTHH')."""
    return f"{ts[:13]}:00:00+00:00"


def _row_to_measurement(row: aiosqlite.Row) -> MeasurementOut:
    keys = row.keys()

    def opt(name: str):
        return row[name] if name in keys else None

    return MeasurementOut(
        id=row["id"],
        target_id=row["target_id"],
        target_name=opt("name"),
        timestamp=row["timestamp"],
        latency_ms=row["latency_ms"],
        packet_loss=row["packet_loss"],
        jitter_ms=row["jitter_ms"],
        success=bool(row["success"]),
        error=row["error"],
        network_name=opt("network_name"),
        median_ms=opt("median_ms"),
        p25_ms=opt("p25_ms"),
        p75_ms=opt("p75_ms"),
        p95_ms=opt("p95_ms"),
        min_ms=opt("min_ms"),
        max_ms=opt("max_ms"),
        iqr_ms=opt("iqr_ms"),
        jitter_rfc3550=opt("jitter_rfc3550"),
        packet_count=opt("packet_count"),
    )


def _hourly_row_to_measurement(row: aiosqlite.Row, synthetic_id: int) -> MeasurementOut:
    """An hourly rollup row presented in the raw-measurement shape, so the
    History chart / CSV export / CLI keep working across the raw->hourly
    boundary. ``id`` is a negative synthetic number (hourly rows have none)."""
    loss = row["avg_loss_pct"]
    return MeasurementOut(
        id=synthetic_id,
        target_id=row["target_id"],
        target_name=row["name"],
        timestamp=row["hour_bucket"],
        latency_ms=row["avg_median_ms"],
        packet_loss=loss,
        jitter_ms=row["avg_jitter_ms"],
        success=loss < 100,
        error=DOWNSAMPLED_MARKER,
        network_name=None,
        median_ms=row["avg_median_ms"],
        iqr_ms=row["avg_iqr_ms"],
        p95_ms=row["max_p95_ms"],
        min_ms=row["min_ms"],
        max_ms=row["max_ms"],
        jitter_rfc3550=row["avg_jitter_ms"],
    )


# ---------------------------------------------------------------- writes


async def insert_measurement(conn: aiosqlite.Connection, data: MeasurementCreate) -> int:
    async with write_transaction() as tx:
        cursor = await tx.execute(
            """
            INSERT INTO measurements (
                target_id, timestamp, latency_ms, packet_loss, jitter_ms, success, error, network_name,
                median_ms, p25_ms, p75_ms, p95_ms, min_ms, max_ms, iqr_ms, jitter_rfc3550, packet_count
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                data.median_ms,
                data.p25_ms,
                data.p75_ms,
                data.p95_ms,
                data.min_ms,
                data.max_ms,
                data.iqr_ms,
                data.jitter_rfc3550,
                data.packet_count,
            ),
        )
    return int(cursor.lastrowid or 0)


# ----------------------------------------------------------------- reads


def _raw_filters(target_id: int | None, start: str | None, end: str | None) -> tuple[str, list]:
    clause = ""
    params: list = []
    if target_id is not None:
        clause += " AND m.target_id = ?"
        params.append(target_id)
    if start is not None:
        clause += " AND m.timestamp >= ?"
        params.append(start)
    if end is not None:
        clause += " AND m.timestamp <= ?"
        params.append(end)
    return clause, params


# Hourly buckets that are strictly older than the oldest raw row of the same
# target - i.e. the part of history that only exists in the hourly tier. The
# rollup job never leaves raw and hourly rows for the same hour, so this is
# just a guard against double counting.
_HOURLY_OLDER_THAN_RAW = (
    "h.hour_bucket < COALESCE((SELECT MIN(r.timestamp) FROM measurements r WHERE r.target_id = h.target_id), ?)"
)


def _hourly_filters(target_id: int | None, start: str | None, end: str | None) -> tuple[str, list]:
    clause = f" AND {_HOURLY_OLDER_THAN_RAW}"
    params: list = [_FAR_FUTURE]
    if target_id is not None:
        clause += " AND h.target_id = ?"
        params.append(target_id)
    if start is not None:
        clause += " AND h.hour_bucket >= ?"
        params.append(_hour_floor_iso(start))
    if end is not None:
        clause += " AND h.hour_bucket <= ?"
        params.append(end)
    return clause, params


def decimate_measurements(rows: list[MeasurementOut], target_count: int) -> list[MeasurementOut]:
    """Uniformly downsample rows to at most target_count items, preserving endpoints."""
    if len(rows) <= target_count or target_count < 2:
        return rows
    step = (len(rows) - 1) / (target_count - 1)
    indices = {int(round(i * step)) for i in range(target_count)}
    return [rows[i] for i in sorted(indices)]


async def list_measurements(
    conn: aiosqlite.Connection,
    *,
    target_id: int | None = None,
    start: str | None = None,
    end: str | None = None,
    limit: int = 1000,
    decimate_to: int | None = None,
) -> list[MeasurementOut]:
    """Newest first. Raw checks first; when they do not fill ``limit`` the
    remainder is topped up from the hourly rollup tier (older history)."""
    where, params = _raw_filters(target_id, start, end)
    query = (
        "SELECT m.*, t.name FROM measurements m JOIN targets t ON t.id = m.target_id "
        f"WHERE 1=1{where} ORDER BY m.timestamp DESC, m.id DESC LIMIT ?"
    )
    async with conn.execute(query, [*params, limit]) as cursor:
        rows = [_row_to_measurement(r) for r in await cursor.fetchall()]

    remaining = limit - len(rows)
    if remaining > 0:
        h_where, h_params = _hourly_filters(target_id, start, end)
        h_query = (
            "SELECT h.*, t.name FROM ping_metrics_hourly h JOIN targets t ON t.id = h.target_id "
            f"WHERE 1=1{h_where} ORDER BY h.hour_bucket DESC, h.target_id DESC LIMIT ?"
        )
        async with conn.execute(h_query, [*h_params, remaining]) as cursor:
            hourly = await cursor.fetchall()
        rows.extend(_hourly_row_to_measurement(r, -(i + 1)) for i, r in enumerate(hourly))
    if decimate_to is not None and decimate_to > 0:
        return decimate_measurements(rows, decimate_to)
    return rows


async def iter_measurements(
    conn: aiosqlite.Connection,
    *,
    target_id: int | None = None,
    start: str | None = None,
    end: str | None = None,
    batch_size: int = 1000,
    max_rows: int | None = None,
) -> AsyncIterator[MeasurementOut]:
    """
    Same rows and order as list_measurements (raw, then hourly), but lazily:
    memory stays O(batch_size) however large the export is.

    Pages with keyset pagination - one short query per batch - rather than
    holding a cursor open between yields. An open read cursor on a slow
    download would pin a WAL snapshot and stop the WAL from being checkpointed
    for as long as the client takes to read.
    """
    yielded = 0

    # Raw tier: (timestamp DESC, id DESC)
    after: tuple[str, int] | None = None
    while True:
        where, params = _raw_filters(target_id, start, end)
        if after is not None:
            where += " AND (m.timestamp < ? OR (m.timestamp = ? AND m.id < ?))"
            params += [after[0], after[0], after[1]]
        query = (
            "SELECT m.*, t.name FROM measurements m JOIN targets t ON t.id = m.target_id "
            f"WHERE 1=1{where} ORDER BY m.timestamp DESC, m.id DESC LIMIT ?"
        )
        async with conn.execute(query, [*params, batch_size]) as cursor:
            rows = list(await cursor.fetchall())
        for row in rows:
            if max_rows is not None and yielded >= max_rows:
                return
            yield _row_to_measurement(row)
            yielded += 1
        if len(rows) < batch_size:
            break
        after = (rows[-1]["timestamp"], rows[-1]["id"])

    # Hourly tier: (hour_bucket DESC, target_id DESC)
    after_h: tuple[str, int] | None = None
    synthetic = 0
    while True:
        h_where, h_params = _hourly_filters(target_id, start, end)
        if after_h is not None:
            h_where += " AND (h.hour_bucket < ? OR (h.hour_bucket = ? AND h.target_id < ?))"
            h_params += [after_h[0], after_h[0], after_h[1]]
        h_query = (
            "SELECT h.*, t.name FROM ping_metrics_hourly h JOIN targets t ON t.id = h.target_id "
            f"WHERE 1=1{h_where} ORDER BY h.hour_bucket DESC, h.target_id DESC LIMIT ?"
        )
        async with conn.execute(h_query, [*h_params, batch_size]) as cursor:
            h_rows = list(await cursor.fetchall())
        for row in h_rows:
            if max_rows is not None and yielded >= max_rows:
                return
            synthetic += 1
            yield _hourly_row_to_measurement(row, -synthetic)
            yielded += 1
        if len(h_rows) < batch_size:
            break
        after_h = (h_rows[-1]["hour_bucket"], h_rows[-1]["target_id"])


async def latest_measurement(conn: aiosqlite.Connection, target_id: int) -> MeasurementOut | None:
    async with conn.execute(
        "SELECT m.*, t.name FROM measurements m JOIN targets t ON t.id = m.target_id "
        "WHERE m.target_id = ? ORDER BY m.timestamp DESC, m.id DESC LIMIT 1",
        (target_id,),
    ) as cursor:
        row = await cursor.fetchone()
    return _row_to_measurement(row) if row else None


async def latest_measurements_all(conn: aiosqlite.Connection) -> list[MeasurementOut]:
    """
    Most recent measurement per enabled target - used for the live status view,
    which the dashboard polls every few seconds. One index seek per target
    (idx_measurements_target_ts) instead of a GROUP BY over every stored row.
    """
    query = """
        SELECT m.*, t.name FROM targets t
        JOIN measurements m ON m.id = (
            SELECT id FROM measurements WHERE target_id = t.id ORDER BY timestamp DESC, id DESC LIMIT 1
        )
        WHERE t.enabled = 1
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


# ------------------------------------------------------------ statistics


async def latency_points_in_range(
    conn: aiosqlite.Connection, *, target_id: int | None, start: str, end: str
) -> list[tuple[float, float]]:
    """(median latency, p95) of every successful check in range. p95 falls back to the
    latency itself for checks recorded before Burst Probing (which have no p95)."""
    query = (
        "SELECT latency_ms, COALESCE(p95_ms, latency_ms) AS p95 FROM measurements "
        "WHERE timestamp BETWEEN ? AND ? AND latency_ms IS NOT NULL"
    )
    params: list = [start, end]
    if target_id is not None:
        query += " AND target_id = ?"
        params.append(target_id)
    async with conn.execute(query, params) as cursor:
        rows = await cursor.fetchall()
    return [(r["latency_ms"], r["p95"]) for r in rows]


async def aggregate_in_range(conn: aiosqlite.Connection, *, target_id: int | None, start: str, end: str) -> dict:
    query = """
        SELECT
            COUNT(*) AS sample_count,
            AVG(packet_loss) AS avg_packet_loss,
            AVG(jitter_ms) AS avg_jitter,
            AVG(iqr_ms) AS avg_iqr,
            MIN(COALESCE(min_ms, latency_ms)) AS min_rtt,
            MAX(COALESCE(max_ms, latency_ms)) AS max_rtt,
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


async def hourly_rows_in_range(
    conn: aiosqlite.Connection, *, target_id: int | None, start: str, end: str
) -> list[dict]:
    """Hourly rollup buckets overlapping [start, end] that are older than the
    raw tier (see _HOURLY_OLDER_THAN_RAW), oldest first."""
    h_where, h_params = _hourly_filters(target_id, start, end)
    query = f"SELECT h.* FROM ping_metrics_hourly h WHERE 1=1{h_where} ORDER BY h.hour_bucket"
    async with conn.execute(query, h_params) as cursor:
        return [dict(r) for r in await cursor.fetchall()]


async def coverage_bounds(
    conn: aiosqlite.Connection, *, target_id: int | None, start: str, end: str
) -> tuple[str | None, str | None]:
    """
    (first, last) timestamp of data inside [start, end] across both tiers: the
    window over which uptime% is measured. Each MIN/MAX over the indexed
    timestamp is a single b-tree seek, so this stays cheap enough for the
    dashboard's every-few-seconds status poll - unlike loading the rows.
    """
    query = (
        "SELECT MIN(timestamp) AS first_ts, MAX(timestamp) AS last_ts FROM measurements WHERE timestamp BETWEEN ? AND ?"
    )
    params: list = [start, end]
    if target_id is not None:
        query += " AND target_id = ?"
        params.append(target_id)
    async with conn.execute(query, params) as cursor:
        row = await cursor.fetchone()
    first, last = (row["first_ts"], row["last_ts"]) if row else (None, None)

    # Only reach into the hourly tier when the range starts before the raw tier does.
    if first is None or first > start:
        h_where, h_params = _hourly_filters(target_id, start, end)
        h_query = f"SELECT MIN(h.hour_bucket) AS first_b, MAX(h.hour_bucket) AS last_b FROM ping_metrics_hourly h WHERE 1=1{h_where}"
        async with conn.execute(h_query, h_params) as cursor:
            h_row = await cursor.fetchone()
        if h_row and h_row["first_b"] is not None:
            first = h_row["first_b"] if first is None else min(first, h_row["first_b"])
            last = h_row["last_b"] if last is None else max(last, h_row["last_b"])
    return first, last


async def earliest_timestamp(conn: aiosqlite.Connection) -> str | None:
    async with conn.execute("SELECT MIN(timestamp) AS ts FROM measurements") as cursor:
        row = await cursor.fetchone()
    return row["ts"] if row else None


# ------------------------------------------------ retention & rollup


@dataclass(frozen=True)
class RollupResult:
    buckets_written: int
    raw_rows_deleted: int


def _merge_avg(col: str) -> str:
    """ON CONFLICT merge of an AVG column, weighted by sample_count (NULL-safe)."""
    t = "ping_metrics_hourly"
    return (
        f"{col} = CASE WHEN {t}.{col} IS NULL THEN excluded.{col} WHEN excluded.{col} IS NULL THEN {t}.{col} "
        f"ELSE ({t}.{col} * {t}.sample_count + excluded.{col} * excluded.sample_count) "
        f"/ ({t}.sample_count + excluded.sample_count) END"
    )


def _merge_extreme(col: str, fn: str) -> str:
    t = "ping_metrics_hourly"
    return (
        f"{col} = CASE WHEN {t}.{col} IS NULL THEN excluded.{col} WHEN excluded.{col} IS NULL THEN {t}.{col} "
        f"ELSE {fn}({t}.{col}, excluded.{col}) END"
    )


_ROLLUP_SQL = f"""
    INSERT INTO ping_metrics_hourly (
        target_id, hour_bucket, avg_median_ms, avg_iqr_ms, max_p95_ms, avg_loss_pct,
        sample_count, min_ms, max_ms, avg_jitter_ms
    )
    SELECT
        target_id,
        substr(timestamp, 1, 13) || ':00:00+00:00' AS hour_bucket,
        AVG(COALESCE(median_ms, latency_ms)),
        AVG(iqr_ms),
        MAX(COALESCE(p95_ms, latency_ms)),
        AVG(packet_loss),
        COUNT(*),
        MIN(COALESCE(min_ms, latency_ms)),
        MAX(COALESCE(max_ms, latency_ms)),
        AVG(COALESCE(jitter_rfc3550, jitter_ms))
    FROM measurements
    WHERE timestamp < :cutoff
    GROUP BY target_id, hour_bucket
    ON CONFLICT(target_id, hour_bucket) DO UPDATE SET
        {_merge_avg("avg_median_ms")},
        {_merge_avg("avg_iqr_ms")},
        {_merge_avg("avg_jitter_ms")},
        {_merge_extreme("max_p95_ms", "max")},
        {_merge_extreme("max_ms", "max")},
        {_merge_extreme("min_ms", "min")},
        avg_loss_pct = (ping_metrics_hourly.avg_loss_pct * ping_metrics_hourly.sample_count
                        + excluded.avg_loss_pct * excluded.sample_count)
                       / (ping_metrics_hourly.sample_count + excluded.sample_count),
        sample_count = ping_metrics_hourly.sample_count + excluded.sample_count
"""


async def rollup_older_than(
    conn: aiosqlite.Connection, *, raw_retention_days: int, now: datetime | None = None
) -> RollupResult:
    """
    Folds raw checks older than ``raw_retention_days`` into one
    ping_metrics_hourly row per target per hour, then deletes those raw rows -
    both in one transaction, so a crash can neither lose nor double-count data.

    The cutoff is floored to the hour, so every hour is rolled up whole, exactly
    once. (The ON CONFLICT merge only exists to stay correct if a late row ever
    lands in an hour that was already rolled up.)
    """
    now = now or datetime.now(timezone.utc)
    cutoff = (now - timedelta(days=raw_retention_days)).replace(minute=0, second=0, microsecond=0).isoformat()

    async with write_transaction() as tx:
        async with tx.execute("SELECT COUNT(*) AS n FROM measurements WHERE timestamp < ?", (cutoff,)) as cursor:
            row = await cursor.fetchone()
        if not row or row["n"] == 0:
            return RollupResult(0, 0)
        cursor = await tx.execute(_ROLLUP_SQL, {"cutoff": cutoff})
        buckets = cursor.rowcount
        cursor = await tx.execute("DELETE FROM measurements WHERE timestamp < ?", (cutoff,))
        deleted = cursor.rowcount
    return RollupResult(buckets_written=buckets, raw_rows_deleted=deleted)


async def delete_hourly_older_than(conn: aiosqlite.Connection, retention_days: int, now: datetime | None = None) -> int:
    now = now or datetime.now(timezone.utc)
    cutoff = (now - timedelta(days=retention_days)).isoformat()
    async with write_transaction() as tx:
        cursor = await tx.execute("DELETE FROM ping_metrics_hourly WHERE hour_bucket < ?", (cutoff,))
    return cursor.rowcount


async def checkpoint_wal(conn: aiosqlite.Connection) -> None:
    """Folds the write-ahead log back into the main file and truncates it, so
    the -wal side file does not sit at its high-water mark between jobs."""
    async with conn.execute("PRAGMA wal_checkpoint(TRUNCATE)") as cursor:
        await cursor.fetchall()


async def vacuum_if_fragmented(
    conn: aiosqlite.Connection, *, min_free_bytes: int = 16 * 1024 * 1024, min_free_ratio: float = 0.3
) -> bool:
    """
    Gives free pages back to the filesystem when there are a lot of them.

    SQLite reuses the space of deleted rows but never shrinks the file by itself,
    so after a big rollup - typically the first one on an install that upgraded
    with days of 5-second checks - the file would stay at its old peak size
    forever. In steady state (hourly rollup, then new rows filling the gap) there
    is little free space and this does nothing. Returns True if it compacted.

    VACUUM rewrites the whole file, so it needs the exclusive writer lock and
    transient disk space; it is gated on both an absolute and a relative amount
    of waste so it only ever runs when it pays for itself. temp_store is switched
    to FILE for the duration, otherwise the rebuilt copy would be held in RAM.
    """

    async def pragma(name: str) -> int:
        async with conn.execute(f"PRAGMA {name}") as cursor:
            row = await cursor.fetchone()
        return int(row[0]) if row else 0

    free_pages, total_pages, page_size = (
        await pragma("freelist_count"),
        await pragma("page_count"),
        await pragma("page_size"),
    )
    if total_pages == 0 or free_pages * page_size < min_free_bytes or free_pages / total_pages < min_free_ratio:
        return False
    try:
        async with write_transaction() as tx:
            await tx.execute("PRAGMA temp_store = FILE")
            try:
                await tx.execute("VACUUM")
            finally:
                await tx.execute("PRAGMA temp_store = MEMORY")
    except aiosqlite.OperationalError:  # pragma: no cover - e.g. disk full; the pass is retried next hour
        return False
    return True
