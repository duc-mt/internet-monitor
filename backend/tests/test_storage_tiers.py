"""
==============================================================================
Module Name:   test_storage_tiers.py
Description:   Burst columns, hourly rollup, retention, tiered reads, streaming export, migrations, PRAGMAs, DB size.
Author:        Mai Tan Duc <ducmai.network@gmail.com>
Created:       2026-10-14
Version:       1.0.0
License:       MIT
==============================================================================
Usage:         pytest backend/tests/test_storage_tiers.py
Notes:         See module docstrings of the code under test.
==============================================================================
"""

from __future__ import annotations

import csv
import io
import json
import random
from datetime import datetime, timedelta, timezone

import aiosqlite
import pytest
from app.database import connection as db_connection
from app.database import measurements_repo, migrations, targets_repo
from app.models.measurement import MeasurementCreate
from app.models.target import TargetCreate
from app.services import settings_service

NOW = datetime(2026, 10, 14, 12, 30, 0, tzinfo=timezone.utc)


def burst_row(
    target_id: int,
    ts: datetime,
    *,
    median: float | None = 20.0,
    iqr: float = 2.0,
    p95: float = 30.0,
    loss: float = 0.0,
    jitter: float = 0.5,
    lo: float = 18.0,
    hi: float = 35.0,
) -> MeasurementCreate:
    ok = median is not None
    return MeasurementCreate(
        target_id=target_id,
        timestamp=ts.isoformat(),
        latency_ms=median,
        packet_loss=loss,
        jitter_ms=jitter if ok else None,
        success=ok,
        median_ms=median,
        p25_ms=(median - iqr / 2) if (ok and median is not None and iqr is not None) else None,
        p75_ms=(median + iqr / 2) if (ok and median is not None and iqr is not None) else None,
        p95_ms=p95 if ok else None,
        min_ms=lo if ok else None,
        max_ms=hi if ok else None,
        iqr_ms=iqr if ok else None,
        jitter_rfc3550=jitter if ok else None,
        packet_count=15,
    )


async def target(db, name="DNS", host="8.8.8.8"):
    return await targets_repo.create_target(db, TargetCreate(name=name, host=host))


# ----------------------------------------------------------- burst columns


async def test_burst_columns_round_trip(db):
    t = await target(db)
    await measurements_repo.insert_measurement(db, burst_row(t.id, NOW, median=21.5, iqr=3.25, p95=40.125, jitter=1.75))
    (row,) = await measurements_repo.list_measurements(db, target_id=t.id)
    assert (row.median_ms, row.p25_ms, row.p75_ms) == (21.5, 19.875, 23.125)
    assert (row.iqr_ms, row.p95_ms, row.jitter_rfc3550, row.packet_count) == (3.25, 40.125, 1.75, 15)
    assert (row.min_ms, row.max_ms) == (18.0, 35.0)


async def test_legacy_rows_without_burst_columns_still_read(db):
    t = await target(db)
    await measurements_repo.insert_measurement(
        db,
        MeasurementCreate(
            target_id=t.id, timestamp=NOW.isoformat(), latency_ms=15.0, packet_loss=0.0, jitter_ms=1.0, success=True
        ),
    )
    (row,) = await measurements_repo.list_measurements(db, target_id=t.id)
    assert row.latency_ms == 15.0 and row.median_ms is None and row.iqr_ms is None and row.packet_count is None


# ----------------------------------------------------------------- rollup


async def test_rollup_folds_old_raw_rows_into_one_hourly_row_and_deletes_them(db):
    t = await target(db)
    base = NOW - timedelta(days=10)
    base = base.replace(minute=0, second=0)
    # 60 one-minute checks in one hour, median 10..., one lossy minute
    for i in range(60):
        await measurements_repo.insert_measurement(
            db,
            burst_row(
                t.id,
                base + timedelta(minutes=i),
                median=10.0 + (i % 2),
                iqr=2.0,
                p95=20.0 + (5 if i == 7 else 0),
                loss=6.67 if i == 3 else 0.0,
                jitter=1.0,
                lo=9.0,
                hi=40.0 if i == 7 else 15.0,
            ),
        )
    recent = NOW - timedelta(hours=1)
    await measurements_repo.insert_measurement(db, burst_row(t.id, recent))

    result = await measurements_repo.rollup_older_than(db, raw_retention_days=7, now=NOW)
    assert (result.buckets_written, result.raw_rows_deleted) == (1, 60)

    async with db.execute("SELECT * FROM ping_metrics_hourly") as cur:
        rows = [dict(r) for r in await cur.fetchall()]
    assert len(rows) == 1
    h = rows[0]
    assert h["hour_bucket"] == base.isoformat()
    assert h["sample_count"] == 60
    assert h["avg_median_ms"] == pytest.approx(10.5)
    assert h["avg_iqr_ms"] == pytest.approx(2.0)
    assert h["max_p95_ms"] == 25.0
    assert h["avg_loss_pct"] == pytest.approx(6.67 / 60)
    assert (h["min_ms"], h["max_ms"]) == (9.0, 40.0)
    assert h["avg_jitter_ms"] == pytest.approx(1.0)

    # only the recent raw row survives in the raw tier
    async with db.execute("SELECT COUNT(*) FROM measurements") as cur:
        assert (await cur.fetchone())[0] == 1


async def test_rollup_is_idempotent_and_never_splits_an_hour(db):
    t = await target(db)
    # an hour that straddles "now - 7d": 12:15 is inside the cutoff hour (12:00), so the whole hour waits
    edge_hour = (NOW - timedelta(days=7)).replace(minute=0, second=0)
    for minute in (5, 20, 50):
        await measurements_repo.insert_measurement(db, burst_row(t.id, edge_hour + timedelta(minutes=minute)))
    first = await measurements_repo.rollup_older_than(db, raw_retention_days=7, now=NOW)
    assert first.raw_rows_deleted == 0  # hour not complete yet: untouched
    later = await measurements_repo.rollup_older_than(db, raw_retention_days=7, now=NOW + timedelta(hours=1))
    assert (later.buckets_written, later.raw_rows_deleted) == (1, 3)
    again = await measurements_repo.rollup_older_than(db, raw_retention_days=7, now=NOW + timedelta(hours=1))
    assert (again.buckets_written, again.raw_rows_deleted) == (0, 0)
    async with db.execute("SELECT sample_count FROM ping_metrics_hourly") as cur:
        assert [r[0] for r in await cur.fetchall()] == [3]


async def test_rollup_merges_a_late_row_into_an_existing_bucket_by_weight(db):
    t = await target(db)
    hour = (NOW - timedelta(days=9)).replace(minute=0, second=0)
    for i in range(3):
        await measurements_repo.insert_measurement(
            db, burst_row(t.id, hour + timedelta(minutes=i), median=10.0, loss=0.0, hi=20.0)
        )
    await measurements_repo.rollup_older_than(db, raw_retention_days=7, now=NOW)
    # a straggler for the same, already rolled-up hour (e.g. clock correction)
    await measurements_repo.insert_measurement(
        db, burst_row(t.id, hour + timedelta(minutes=30), median=30.0, loss=20.0, hi=99.0)
    )
    await measurements_repo.rollup_older_than(db, raw_retention_days=7, now=NOW)
    async with db.execute("SELECT * FROM ping_metrics_hourly") as cur:
        (h,) = (dict(r) for r in await cur.fetchall())
    assert h["sample_count"] == 4
    assert h["avg_median_ms"] == pytest.approx((3 * 10 + 30) / 4)
    assert h["avg_loss_pct"] == pytest.approx(20 / 4)
    assert h["max_ms"] == 99.0


async def test_rollup_handles_legacy_and_all_failed_rows(db):
    t = await target(db)
    hour = (NOW - timedelta(days=9)).replace(minute=0, second=0)
    # legacy (pre-burst) rows: only latency_ms / jitter_ms
    for i, lat in enumerate([10.0, 20.0]):
        await measurements_repo.insert_measurement(
            db,
            MeasurementCreate(
                target_id=t.id,
                timestamp=(hour + timedelta(minutes=i)).isoformat(),
                latency_ms=lat,
                packet_loss=0.0,
                jitter_ms=2.0,
                success=True,
            ),
        )
    # a down hour: every check failed
    down = hour + timedelta(hours=1)
    for i in range(3):
        await measurements_repo.insert_measurement(
            db, burst_row(t.id, down + timedelta(minutes=i), median=None, loss=100.0)
        )
    await measurements_repo.rollup_older_than(db, raw_retention_days=7, now=NOW)
    async with db.execute("SELECT * FROM ping_metrics_hourly ORDER BY hour_bucket") as cur:
        legacy, dead = (dict(r) for r in await cur.fetchall())
    assert legacy["avg_median_ms"] == 15.0 and legacy["max_p95_ms"] == 20.0 and legacy["avg_iqr_ms"] is None
    assert legacy["avg_jitter_ms"] == 2.0
    assert dead["avg_median_ms"] is None and dead["avg_loss_pct"] == 100.0 and dead["sample_count"] == 3


async def test_rollup_is_per_target(db):
    a, b = await target(db, "A", "1.1.1.1"), await target(db, "B", "9.9.9.9")
    hour = (NOW - timedelta(days=9)).replace(minute=0, second=0)
    await measurements_repo.insert_measurement(db, burst_row(a.id, hour, median=10.0))
    await measurements_repo.insert_measurement(db, burst_row(b.id, hour, median=50.0))
    await measurements_repo.rollup_older_than(db, raw_retention_days=7, now=NOW)
    async with db.execute("SELECT target_id, avg_median_ms FROM ping_metrics_hourly ORDER BY target_id") as cur:
        assert [(r[0], r[1]) for r in await cur.fetchall()] == [(a.id, 10.0), (b.id, 50.0)]


async def test_hourly_retention_drops_only_buckets_past_the_limit(db):
    t = await target(db)
    old, fresh = NOW - timedelta(days=100), NOW - timedelta(days=20)
    for ts in (old, fresh):
        await measurements_repo.insert_measurement(db, burst_row(t.id, ts.replace(minute=0, second=0)))
    await measurements_repo.rollup_older_than(db, raw_retention_days=7, now=NOW)
    removed = await measurements_repo.delete_hourly_older_than(db, 90, now=NOW)
    assert removed == 1
    async with db.execute("SELECT hour_bucket FROM ping_metrics_hourly") as cur:
        assert [r[0] for r in await cur.fetchall()] == [fresh.replace(minute=0, second=0).isoformat()]


async def test_run_maintenance_uses_settings_and_checkpoints(db):
    t = await target(db)
    ts = (datetime.now(timezone.utc) - timedelta(days=12)).replace(minute=0, second=0, microsecond=0)
    await measurements_repo.insert_measurement(db, burst_row(t.id, ts))
    from app.monitoring.scheduler import MonitoringManager

    await MonitoringManager.run_maintenance(db)
    async with db.execute("SELECT COUNT(*) FROM measurements") as cur:
        assert (await cur.fetchone())[0] == 0
    async with db.execute("SELECT COUNT(*) FROM ping_metrics_hourly") as cur:
        assert (await cur.fetchone())[0] == 1


async def test_vacuum_gives_space_back_after_a_big_rollup_and_leaves_steady_state_alone(db):
    import os

    async with db.execute("PRAGMA database_list") as cur:
        path = (await cur.fetchone())["file"]  # the fixture's temp file, not the app's default path

    t = await target(db)
    start = NOW - timedelta(days=12)
    batch = [
        (
            t.id,
            (start + timedelta(minutes=i)).isoformat(),
            20.0,
            0.0,
            1.0,
            1,
            None,
            "HomeWiFi",
            20.0,
            18.0,
            22.0,
            30.0,
            15.0,
            40.0,
            4.0,
            1.0,
            15,
        )
        for i in range(12 * 1440)
    ]
    await db.executemany(
        "INSERT INTO measurements (target_id, timestamp, latency_ms, packet_loss, jitter_ms, success, error, network_name, "
        "median_ms, p25_ms, p75_ms, p95_ms, min_ms, max_ms, iqr_ms, jitter_rfc3550, packet_count) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        batch,
    )
    await db.commit()
    await measurements_repo.checkpoint_wal(db)
    big = os.path.getsize(path)

    # Nothing to reclaim yet: too little free space -> no-op, file untouched.
    assert await measurements_repo.vacuum_if_fragmented(db, min_free_bytes=1024) is False
    assert os.path.getsize(path) == big

    await measurements_repo.rollup_older_than(db, raw_retention_days=1, now=NOW)  # deletes ~11 of 12 days
    await measurements_repo.checkpoint_wal(db)
    assert os.path.getsize(path) >= big  # SQLite keeps the freed pages (it even grew a little for the hourly rows)

    assert await measurements_repo.vacuum_if_fragmented(db, min_free_bytes=1024, min_free_ratio=0.3) is True
    await measurements_repo.checkpoint_wal(db)
    assert os.path.getsize(path) < big * 0.4
    # data is intact and the connection still works with its PRAGMAs
    assert len(await measurements_repo.list_measurements(db, target_id=t.id, limit=50000)) > 1440
    async with db.execute("PRAGMA temp_store") as cur:
        assert (await cur.fetchone())[0] == 2  # back to MEMORY
    # and a second call finds nothing worth doing
    assert await measurements_repo.vacuum_if_fragmented(db, min_free_bytes=1024) is False


# --------------------------------------------------------------- tiered reads


async def test_list_measurements_serves_old_history_from_the_hourly_tier(db):
    t = await target(db)
    hour = (NOW - timedelta(days=20)).replace(minute=0, second=0)
    for i in range(5):
        await measurements_repo.insert_measurement(
            db, burst_row(t.id, hour + timedelta(minutes=i), median=12.0, iqr=4.0, p95=33.0)
        )
    await measurements_repo.insert_measurement(db, burst_row(t.id, NOW - timedelta(minutes=5), median=22.0))
    await measurements_repo.rollup_older_than(db, raw_retention_days=7, now=NOW)

    rows = await measurements_repo.list_measurements(db, target_id=t.id, limit=100)
    assert [r.median_ms for r in rows] == [22.0, 12.0]  # newest raw first, then the hourly bucket
    hourly = rows[1]
    assert hourly.timestamp == hour.isoformat() and hourly.error == "Downsampled" and hourly.id < 0
    assert (hourly.latency_ms, hourly.iqr_ms, hourly.p95_ms, hourly.packet_loss) == (12.0, 4.0, 33.0, 0.0)
    assert hourly.target_name == "DNS" and hourly.success is True

    # a window that only covers the recent past never touches the hourly tier
    recent_only = await measurements_repo.list_measurements(
        db, target_id=t.id, start=(NOW - timedelta(hours=1)).isoformat(), limit=100
    )
    assert [r.median_ms for r in recent_only] == [22.0]
    # limit is honoured across tiers
    assert len(await measurements_repo.list_measurements(db, target_id=t.id, limit=1)) == 1


async def test_coverage_bounds_spans_both_tiers(db):
    t = await target(db)
    old = (NOW - timedelta(days=20)).replace(minute=0, second=0)
    await measurements_repo.insert_measurement(db, burst_row(t.id, old))
    await measurements_repo.insert_measurement(db, burst_row(t.id, NOW - timedelta(minutes=5)))
    await measurements_repo.rollup_older_than(db, raw_retention_days=7, now=NOW)
    first, last = await measurements_repo.coverage_bounds(
        db, target_id=t.id, start=(NOW - timedelta(days=30)).isoformat(), end=NOW.isoformat()
    )
    assert first == old.isoformat() and last == (NOW - timedelta(minutes=5)).isoformat()
    # a 24h window is answered from raw alone
    first24, _ = await measurements_repo.coverage_bounds(
        db, target_id=t.id, start=(NOW - timedelta(hours=24)).isoformat(), end=NOW.isoformat()
    )
    assert first24 == (NOW - timedelta(minutes=5)).isoformat()


async def test_latest_measurements_all_is_latest_per_enabled_target(db):
    a, b = await target(db, "A", "1.1.1.1"), await target(db, "B", "9.9.9.9")
    for i, lat in enumerate([5.0, 6.0, 7.0]):
        await measurements_repo.insert_measurement(db, burst_row(a.id, NOW + timedelta(seconds=i), median=lat))
    await measurements_repo.insert_measurement(db, burst_row(b.id, NOW, median=50.0))
    latest = {m.target_id: m.median_ms for m in await measurements_repo.latest_measurements_all(db)}
    assert latest == {a.id: 7.0, b.id: 50.0}
    await targets_repo.update_target(
        db, b.id, __import__("app.models.target", fromlist=["TargetUpdate"]).TargetUpdate(enabled=False)
    )
    assert {m.target_id for m in await measurements_repo.latest_measurements_all(db)} == {a.id}


# ---------------------------------------------------------------- streaming


async def test_iter_measurements_matches_list_and_pages_in_small_batches(db):
    t = await target(db)
    for i in range(25):  # includes identical timestamps to exercise the keyset tie-break
        await measurements_repo.insert_measurement(
            db, burst_row(t.id, NOW - timedelta(minutes=i // 2), median=float(i))
        )
    expected = await measurements_repo.list_measurements(db, target_id=t.id, limit=1000)
    streamed = [m async for m in measurements_repo.iter_measurements(db, target_id=t.id, batch_size=4)]
    assert [m.id for m in streamed] == [m.id for m in expected]
    assert len({m.id for m in streamed}) == 25  # no duplicates, no gaps across batch boundaries


async def test_iter_measurements_continues_into_the_hourly_tier_and_honours_max_rows(db):
    t = await target(db)
    old = (NOW - timedelta(days=15)).replace(minute=0, second=0)
    for h in range(5):
        await measurements_repo.insert_measurement(db, burst_row(t.id, old + timedelta(hours=h), median=float(h)))
    for i in range(3):
        await measurements_repo.insert_measurement(db, burst_row(t.id, NOW - timedelta(minutes=i), median=100.0 + i))
    await measurements_repo.rollup_older_than(db, raw_retention_days=7, now=NOW)

    everything = [m async for m in measurements_repo.iter_measurements(db, batch_size=2)]
    assert len(everything) == 8
    assert [m.timestamp for m in everything] == sorted((m.timestamp for m in everything), reverse=True)
    capped = [m async for m in measurements_repo.iter_measurements(db, batch_size=2, max_rows=4)]
    assert len(capped) == 4


async def test_export_streams_without_materialising_all_rows(client):
    """The CSV endpoint must go through iter_measurements (lazy), not list_measurements(limit=100000)."""
    from app.api import export

    # Seed rows through the app's own DB connection.
    conn = db_connection.get_connection()
    t = await targets_repo.create_target(conn, TargetCreate(name="EXP", host="1.2.3.4"))
    for i in range(30):
        await measurements_repo.insert_measurement(conn, burst_row(t.id, NOW - timedelta(minutes=i), median=float(i)))

    calls = {"list": 0}
    original_list = measurements_repo.list_measurements

    async def spy(*a, **k):
        calls["list"] += 1
        return await original_list(*a, **k)

    measurements_repo.list_measurements = spy  # type: ignore[assignment]
    try:
        response = client.get("/api/export/measurements.csv", params={"target_id": t.id})
    finally:
        measurements_repo.list_measurements = original_list  # type: ignore[assignment]

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert calls["list"] == 0
    rows = list(csv.reader(io.StringIO(response.text)))
    assert rows[0] == export.CSV_COLUMNS
    assert len(rows) == 31
    # legacy columns keep their positions; burst columns are appended
    assert rows[0][:9] == [
        "timestamp",
        "target_id",
        "target_name",
        "latency_ms",
        "packet_loss",
        "jitter_ms",
        "success",
        "error",
        "network_name",
    ]
    first = dict(zip(rows[0], rows[1]))
    assert first["median_ms"] == "0.0" and first["packet_count"] == "15" and first["iqr_ms"] == "2.0"


def test_export_report_json_still_works(client):
    r = client.get("/api/export/report.json")
    assert r.status_code == 200
    body = json.loads(r.text)
    assert "statistics" in body and "outages" in body and "avg_iqr_ms" in body["statistics"]


# --------------------------------------------------------------- migrations


async def _old_database(path):
    """A database as the previous release left it: old columns only, old defaults stored."""
    async with aiosqlite.connect(path) as conn:
        await conn.executescript(
            """
            CREATE TABLE targets (id INTEGER PRIMARY KEY, name TEXT NOT NULL, host TEXT NOT NULL, protocol TEXT NOT NULL DEFAULT 'icmp',
              port INTEGER, enabled INTEGER NOT NULL DEFAULT 1, is_gateway INTEGER NOT NULL DEFAULT 0, interval_seconds INTEGER NOT NULL DEFAULT 5,
              created_at TEXT NOT NULL DEFAULT '2026-01-01T00:00:00+00:00');
            CREATE TABLE measurements (id INTEGER PRIMARY KEY AUTOINCREMENT, target_id INTEGER NOT NULL, timestamp TEXT NOT NULL,
              latency_ms REAL, packet_loss REAL NOT NULL, jitter_ms REAL, success INTEGER NOT NULL, error TEXT, network_name TEXT);
            CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            INSERT INTO targets (id, name, host, interval_seconds) VALUES (1, 'DNS', '8.8.8.8', 5), (2, 'Custom', '1.1.1.1', 30);
            INSERT INTO measurements (target_id, timestamp, latency_ms, packet_loss, jitter_ms, success)
              VALUES (1, '2026-10-10T00:00:00+00:00', 12.0, 0.0, 1.0, 1);
            """
        )
        await conn.execute(
            "INSERT INTO settings (key, value) VALUES ('app_settings', ?)",
            (
                json.dumps(
                    {
                        "default_target_interval_seconds": 5,
                        "data_retention_days": 30,
                        "pings_per_check": 3,
                        "theme": "dark",
                    }
                ),
            ),
        )
        await conn.commit()


async def test_upgrade_from_the_previous_release_keeps_data_and_moves_old_defaults(tmp_path):
    path = tmp_path / "old.db"
    await _old_database(path)
    conn = await db_connection.init_db(path)
    try:
        # old row survived and gained the new (NULL) columns
        (row,) = await measurements_repo.list_measurements(conn, target_id=1)
        assert row.latency_ms == 12.0 and row.median_ms is None
        # targets on the old default moved to 60 s; a user-chosen 30 s was left alone
        async with conn.execute("SELECT id, interval_seconds FROM targets ORDER BY id") as cur:
            assert [(r[0], r[1]) for r in await cur.fetchall()] == [(1, 60), (2, 30)]
        settings_service.invalidate_cache()
        s = await settings_service.get_settings(conn)
        assert (s.default_target_interval_seconds, s.data_retention_days, s.theme) == (60, 90, "dark")
        async with conn.execute("PRAGMA user_version") as cur:
            assert (await cur.fetchone())[0] == migrations.SCHEMA_VERSION
    finally:
        await db_connection.close_db()

    # second start: idempotent, and a value the user sets afterwards is not "migrated" again
    conn = await db_connection.init_db(path)
    try:
        await conn.execute("UPDATE targets SET interval_seconds = 5 WHERE id = 2")
        await conn.commit()
    finally:
        await db_connection.close_db()
    conn = await db_connection.init_db(path)
    try:
        async with conn.execute("SELECT interval_seconds FROM targets WHERE id = 2") as cur:
            assert (await cur.fetchone())[0] == 5
    finally:
        await db_connection.close_db()


async def test_fresh_database_has_the_new_schema(db):
    async with db.execute("PRAGMA table_info(measurements)") as cur:
        cols = {r["name"] for r in await cur.fetchall()}
    assert {
        "median_ms",
        "p25_ms",
        "p75_ms",
        "p95_ms",
        "min_ms",
        "max_ms",
        "iqr_ms",
        "jitter_rfc3550",
        "packet_count",
    } <= cols
    async with db.execute("PRAGMA table_info(ping_metrics_hourly)") as cur:
        hourly = {r["name"] for r in await cur.fetchall()}
    assert {
        "target_id",
        "hour_bucket",
        "avg_median_ms",
        "avg_iqr_ms",
        "max_p95_ms",
        "avg_loss_pct",
        "sample_count",
    } <= hourly


# ------------------------------------------------------------------- PRAGMAs


async def test_connection_is_opened_with_wal_normal_and_memory_temp_store(db):
    async def pragma(name):
        async with db.execute(f"PRAGMA {name}") as cur:
            return (await cur.fetchone())[0]

    assert str(await pragma("journal_mode")).lower() == "wal"
    assert await pragma("synchronous") == 1  # NORMAL
    assert await pragma("temp_store") == 2  # MEMORY
    assert await pragma("foreign_keys") == 1


# ------------------------------------------------------------------ DB size


async def test_measured_per_row_cost_keeps_the_default_footprint_under_50mb(db):
    """
    Guards the storage budget: measures the real bytes per raw row and per hourly row from
    SQLite's own page accounting (so adding a column or an index shows up here), then
    projects the default configuration - 60 s bursts, 7 days raw + 83 days hourly - for 20 targets.
    (tools: a full 90-day simulation of 5 targets measured 13.8 MB; see README "Storage".)
    """
    try:
        async with db.execute("SELECT SUM(pgsize) FROM dbstat") as cur:
            await cur.fetchone()
    except aiosqlite.OperationalError:
        pytest.skip("this SQLite build has no dbstat virtual table")

    async def table_bytes(*names: str) -> int:
        total = 0
        for name in names:
            async with db.execute("SELECT COALESCE(SUM(pgsize), 0) FROM dbstat WHERE name = ?", (name,)) as cur:
                total += (await cur.fetchone())[0]
        return total

    rng = random.Random(7)
    targets = [await target(db, f"T{i}", f"10.0.0.{i + 1}") for i in range(3)]
    days = 12
    start = (NOW - timedelta(days=days)).replace(minute=0, second=0)
    rows = 0
    for t in targets:
        batch = []
        for minute in range(days * 1440):
            m = burst_row(
                t.id,
                start + timedelta(minutes=minute),
                median=rng.uniform(8, 40),
                iqr=rng.uniform(0.5, 6),
                p95=rng.uniform(30, 90),
                loss=rng.choice([0.0] * 20 + [6.67]),
                jitter=rng.uniform(0.1, 3),
            )
            batch.append(
                (
                    m.target_id,
                    m.timestamp,
                    m.latency_ms,
                    m.packet_loss,
                    m.jitter_ms,
                    1,
                    None,
                    "HomeWiFi",
                    m.median_ms,
                    m.p25_ms,
                    m.p75_ms,
                    m.p95_ms,
                    m.min_ms,
                    m.max_ms,
                    m.iqr_ms,
                    m.jitter_rfc3550,
                    m.packet_count,
                )
            )
        await db.executemany(
            "INSERT INTO measurements (target_id, timestamp, latency_ms, packet_loss, jitter_ms, success, error, network_name, "
            "median_ms, p25_ms, p75_ms, p95_ms, min_ms, max_ms, iqr_ms, jitter_rfc3550, packet_count) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            batch,
        )
        rows += len(batch)
    await db.commit()

    raw_bytes_per_row = await table_bytes("measurements", "idx_measurements_target_ts", "idx_measurements_ts") / rows
    await measurements_repo.rollup_older_than(db, raw_retention_days=0, now=NOW)  # roll everything up
    async with db.execute("SELECT COUNT(*) FROM ping_metrics_hourly") as cur:
        hourly_rows = (await cur.fetchone())[0]
    assert hourly_rows == 3 * days * 24
    hourly_bytes_per_row = await table_bytes("ping_metrics_hourly", "idx_hourly_bucket") / hourly_rows

    n_targets = 20
    raw_mb = raw_bytes_per_row * 7 * 1440 * n_targets / 1e6
    hourly_mb = hourly_bytes_per_row * 83 * 24 * n_targets / 1e6
    assert raw_bytes_per_row < 250, raw_bytes_per_row  # measured ~215
    assert hourly_bytes_per_row < 160, hourly_bytes_per_row  # measured ~140
    assert raw_mb + hourly_mb < 55, (raw_mb, hourly_mb)
