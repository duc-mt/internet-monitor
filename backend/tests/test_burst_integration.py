"""
==============================================================================
Module Name:   test_burst_integration.py
Description:   End to end: scheduler stores burst summaries; status, statistics and stability use them.
Author:        Mai Tan Duc <ducmai.network@gmail.com>
Created:       2026-10-14
Version:       1.0.0
License:       MIT
==============================================================================
Usage:         pytest backend/tests/test_burst_integration.py
Notes:         See module docstrings of the code under test.
==============================================================================
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from app.database import measurements_repo, targets_repo
from app.models.measurement import MeasurementCreate
from app.models.settings import StabilityThresholds
from app.models.target import TargetCreate
from app.monitoring import scheduler as monitoring_scheduler
from app.monitoring.burst_stats import BurstMetric, compute_burst_metric
from app.services import quality_service, statistics_service, status_service

S = StabilityThresholds()


async def _status(db):
    return await status_service.compute_status(db, monitoring_started_at=None, monitoring_running=False)


# -------------------------------------------------------------- stability


@pytest.mark.parametrize(
    "iqr, loss, expected",
    [
        (0.0, 0.0, "excellent"),
        (4.99, 0.0, "excellent"),
        (5.0, 0.0, "good"),  # IQR at the boundary is no longer "< 5"
        (4.0, 6.67, "good"),  # one lost probe of 15 is tolerated by "good", never by "excellent"
        (14.9, 0.0, "good"),
        (15.0, 0.0, "fair"),
        (20.0, 13.3, "fair"),
        (29.9, 15.0, "fair"),
        (30.0, 0.0, "poor"),
        (2.0, 20.0, "poor"),
        (2.0, 100.0, "poor"),
    ],
)
def test_classify_stability(iqr, loss, expected):
    assert quality_service.classify_stability(iqr, loss, S) == expected


def test_classify_stability_unknown_without_data_and_honours_custom_thresholds():
    assert quality_service.classify_stability(None, 0.0, S) == "unknown"
    assert quality_service.classify_stability(3.0, None, S) == "unknown"
    strict = StabilityThresholds(excellent_iqr_ms=1)
    assert quality_service.classify_stability(3.0, 0.0, strict) == "good"


# --------------------------------------------------------------- scheduler


async def test_scheduler_stores_the_full_burst_summary(db, monkeypatch):
    t = await targets_repo.create_target(db, TargetCreate(name="DNS", host="8.8.8.8", interval_seconds=60))
    seen = {}

    async def fake_burst(*, host, protocol, port, count, interval_ms, timeout) -> BurstMetric:
        seen.update(host=host, protocol=protocol, count=count, interval_ms=interval_ms, timeout=timeout)
        return compute_burst_metric([10.0 + i for i in range(count)], method="icmp")

    monkeypatch.setattr(monitoring_scheduler, "run_burst", fake_burst)
    manager = monitoring_scheduler.MonitoringManager()
    await manager.start(db)
    try:
        for _ in range(100):
            if await measurements_repo.latest_measurement(db, t.id):
                break
            await asyncio.sleep(0.05)
    finally:
        await manager.stop()

    # the burst parameters come from Settings (defaults: 15 probes, 20 ms apart)
    assert seen["host"] == "8.8.8.8" and seen["count"] == 15 and seen["interval_ms"] == 20

    m = await measurements_repo.latest_measurement(db, t.id)
    assert m is not None
    assert (m.median_ms, m.min_ms, m.max_ms, m.packet_count) == (17.0, 10.0, 24.0, 15)
    assert (m.p25_ms, m.p75_ms, m.iqr_ms) == (13.5, 20.5, 7.0)
    assert m.p95_ms == pytest.approx(23.3) and m.jitter_rfc3550 is not None
    # legacy columns mirror the new ones
    assert m.latency_ms == m.median_ms and m.jitter_ms == m.jitter_rfc3550 and m.packet_loss == 0.0 and m.success


async def test_scheduler_records_a_dead_target_as_full_loss(db, monkeypatch):
    t = await targets_repo.create_target(db, TargetCreate(name="Dead", host="192.0.2.1"))

    async def dead(*, host, protocol, port, count, interval_ms, timeout):
        return compute_burst_metric([None] * count, method="icmp", error="request timed out")

    monkeypatch.setattr(monitoring_scheduler, "run_burst", dead)
    manager = monitoring_scheduler.MonitoringManager()
    await manager.start(db)
    try:
        for _ in range(100):
            if await measurements_repo.latest_measurement(db, t.id):
                break
            await asyncio.sleep(0.05)
    finally:
        await manager.stop()
    m = await measurements_repo.latest_measurement(db, t.id)
    assert (m.success, m.packet_loss, m.median_ms, m.iqr_ms, m.error) == (False, 100.0, None, None, "request timed out")
    assert m.packet_count == 15


# ------------------------------------------------------------------ status


async def _seed(db, target, *, median, iqr, p95, jitter, loss=0.0, ago=timedelta(seconds=5)):
    await measurements_repo.insert_measurement(
        db,
        MeasurementCreate(
            target_id=target.id,
            timestamp=(datetime.now(timezone.utc) - ago).isoformat(),
            latency_ms=median,
            packet_loss=loss,
            jitter_ms=jitter,
            success=True,
            median_ms=median,
            iqr_ms=iqr,
            p95_ms=p95,
            jitter_rfc3550=jitter,
            packet_count=15,
        ),
    )


async def test_status_reports_burst_headline_and_stability(db):
    for existing in await targets_repo.list_targets(db):
        await targets_repo.delete_target(db, existing.id)
    a = await targets_repo.create_target(db, TargetCreate(name="A", host="1.1.1.1"))
    b = await targets_repo.create_target(db, TargetCreate(name="B", host="9.9.9.9"))
    await _seed(db, a, median=10.0, iqr=2.0, p95=18.0, jitter=0.5)
    await _seed(db, b, median=20.0, iqr=4.0, p95=30.0, jitter=1.5)
    status = await _status(db)
    assert (
        status.median_ms == 15.0 and status.iqr_ms == 3.0 and status.p95_ms == 24.0 and status.jitter_rfc3550_ms == 1.0
    )
    assert status.stability == "excellent"
    per_target = {t.name: t for t in status.targets}
    assert (per_target["A"].median_ms, per_target["A"].iqr_ms, per_target["A"].p95_ms) == (10.0, 2.0, 18.0)


async def test_status_stability_degrades_with_iqr_and_goes_unknown_when_offline(db):
    for existing in await targets_repo.list_targets(db):
        await targets_repo.delete_target(db, existing.id)
    a = await targets_repo.create_target(db, TargetCreate(name="A", host="1.1.1.1"))
    await _seed(db, a, median=30.0, iqr=22.0, p95=90.0, jitter=6.0)
    assert (await _status(db)).stability == "fair"


# -------------------------------------------------------- uptime / statistics


async def test_compute_uptime_pct_agrees_with_compute_statistics(db):
    t = await targets_repo.create_target(db, TargetCreate(name="A", host="1.1.1.1"))
    now = datetime.now(timezone.utc)
    for i in range(30):
        await measurements_repo.insert_measurement(
            db,
            MeasurementCreate(
                target_id=t.id,
                timestamp=(now - timedelta(minutes=30 - i)).isoformat(),
                latency_ms=10.0,
                packet_loss=0.0,
                jitter_ms=1.0,
                success=True,
            ),
        )
    light = await statistics_service.compute_uptime_pct(db)
    full = (await statistics_service.compute_statistics(db, range_name="24h")).uptime_pct
    assert light == full == 100.0


async def test_status_does_not_load_the_latency_samples(db, monkeypatch):
    """Regression: /api/status used to run compute_statistics (load + sort a day of samples) on every poll."""
    called = []

    async def boom(*a, **k):
        called.append(1)
        return []

    monkeypatch.setattr(measurements_repo, "latency_points_in_range", boom)
    await _status(db)
    assert called == []


async def test_statistics_span_the_raw_and_hourly_tiers(db):
    t = await targets_repo.create_target(db, TargetCreate(name="A", host="1.1.1.1"))
    now = datetime.now(timezone.utc).replace(microsecond=0)
    old_hour = (now - timedelta(days=20)).replace(minute=0, second=0)
    for i in range(60):  # 20 days ago: 60 checks, median 100, one total-loss minute
        await measurements_repo.insert_measurement(
            db,
            MeasurementCreate(
                target_id=t.id,
                timestamp=(old_hour + timedelta(minutes=i)).isoformat(),
                latency_ms=100.0,
                packet_loss=0.0,
                jitter_ms=4.0,
                success=True,
                median_ms=100.0,
                iqr_ms=8.0,
                p95_ms=140.0,
                min_ms=90.0,
                max_ms=200.0,
                jitter_rfc3550=4.0,
                packet_count=15,
            ),
        )
    for i in range(60):  # last hour: 60 checks, median 20
        await measurements_repo.insert_measurement(
            db,
            MeasurementCreate(
                target_id=t.id,
                timestamp=(now - timedelta(minutes=60 - i)).isoformat(),
                latency_ms=20.0,
                packet_loss=0.0,
                jitter_ms=1.0,
                success=True,
                median_ms=20.0,
                iqr_ms=2.0,
                p95_ms=30.0,
                min_ms=15.0,
                max_ms=45.0,
                jitter_rfc3550=1.0,
                packet_count=15,
            ),
        )
    await measurements_repo.rollup_older_than(db, raw_retention_days=7)

    s = await statistics_service.compute_statistics(db, range_name="30d")
    assert s.sample_count == 120
    assert s.avg_latency_ms == 60.0  # (60 x 100 + 60 x 20) / 120 - the old hour counts at its full weight
    assert (s.min_latency_ms, s.max_latency_ms) == (15.0, 200.0)
    assert s.avg_iqr_ms == 5.0 and s.avg_jitter_ms == 2.5
    assert s.p95_latency_ms == 140.0 and s.median_latency_ms in (20.0, 100.0)
    assert s.monitoring_duration_seconds > 19 * 86400  # coverage reaches back into the hourly tier

    # a 24h window must not see the rolled-up hour at all
    day = await statistics_service.compute_statistics(db, range_name="24h")
    assert day.sample_count == 60 and day.avg_latency_ms == 20.0 and day.avg_iqr_ms == 2.0


async def test_statistics_raw_only_percentiles_are_unchanged(db):
    t = await targets_repo.create_target(db, TargetCreate(name="A", host="1.1.1.1"))
    now = datetime.now(timezone.utc)
    for i, lat in enumerate([10.0, 20.0, 30.0, 40.0]):
        await measurements_repo.insert_measurement(
            db,
            MeasurementCreate(
                target_id=t.id,
                timestamp=(now - timedelta(minutes=i)).isoformat(),
                latency_ms=lat,
                packet_loss=0.0,
                jitter_ms=None,
                success=True,
            ),
        )
    s = await statistics_service.compute_statistics(db, range_name="1h")
    assert s.median_latency_ms == 25.0 and s.p95_latency_ms == 38.5 and s.avg_iqr_ms is None


def test_weighted_percentile_nearest_rank():
    assert statistics_service.weighted_percentile([(10, 1), (20, 1), (30, 8)], 50) == 30
    assert statistics_service.weighted_percentile([(10, 8), (20, 1), (30, 1)], 90) == 20
    assert statistics_service.weighted_percentile([(10, 8), (20, 1), (30, 1)], 95) == 30
    assert statistics_service.weighted_percentile([(5, 1)], 95) == 5


async def test_api_exposes_the_new_fields(client):
    status = client.get("/api/status").json()
    for key in ("median_ms", "iqr_ms", "p95_ms", "jitter_rfc3550_ms", "stability"):
        assert key in status
    assert status["stability"] == "unknown"  # nothing measured yet
    m = client.get("/api/measurements").json()
    assert isinstance(m, list)
    stats = client.get("/api/statistics?range=24h").json()
    assert "avg_iqr_ms" in stats
