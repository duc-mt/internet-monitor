from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.database import targets_repo
from app.database.measurements_repo import insert_measurement
from app.models.measurement import MeasurementCreate
from app.models.target import TargetCreate
from app.services import statistics_service


def test_percentile_of_single_value():
    assert statistics_service.percentile([42.0], 95) == 42.0


def test_percentile_linear_interpolation():
    # sorted [10,20,30,40,50], p50 index=(0.5*4)=2 -> value 30
    values = [10.0, 20.0, 30.0, 40.0, 50.0]
    assert statistics_service.percentile(values, 50) == 30.0
    # p95 index = 0.95*4 = 3.8 -> interpolate between values[3]=40 and values[4]=50
    assert statistics_service.percentile(values, 95) == pytest.approx(48.0)


def test_resolve_range_named():
    start, end = statistics_service.resolve_range("1h", None, None)
    assert (end - start) == timedelta(hours=1)


def test_resolve_range_custom_requires_bounds():
    with pytest.raises(ValueError):
        statistics_service.resolve_range("custom", None, None)


def test_resolve_range_custom_rejects_backwards_range():
    now = datetime.now(timezone.utc)
    with pytest.raises(ValueError):
        statistics_service.resolve_range("custom", now.isoformat(), (now - timedelta(hours=1)).isoformat())


def test_resolve_range_unknown_name():
    with pytest.raises(ValueError):
        statistics_service.resolve_range("nonsense", None, None)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_compute_statistics_end_to_end(db):
    target = await targets_repo.create_target(db, TargetCreate(name="Test", host="1.1.1.1", protocol="icmp"))
    now = datetime.now(timezone.utc)

    samples = [10.0, 20.0, 30.0, 40.0, 50.0]
    for i, latency in enumerate(samples):
        await insert_measurement(db, MeasurementCreate(
            target_id=target.id,
            timestamp=(now - timedelta(minutes=len(samples) - i)).isoformat(),
            latency_ms=latency,
            packet_loss=0.0,
            jitter_ms=1.0,
            success=True,
        ))
    # one failed check
    await insert_measurement(db, MeasurementCreate(
        target_id=target.id, timestamp=now.isoformat(),
        latency_ms=None, packet_loss=100.0, jitter_ms=None, success=False, error="timeout",
    ))

    stats = await statistics_service.compute_statistics(db, range_name="1h", target_id=target.id)
    assert stats.sample_count == 6
    assert stats.min_latency_ms == 10.0
    assert stats.max_latency_ms == 50.0
    assert stats.median_latency_ms == 30.0
    assert stats.avg_latency_ms == 30.0
    assert stats.packet_loss_pct == pytest.approx(100 / 6, rel=0.01)
