from __future__ import annotations
"""
==============================================================================
Module Name:   test_measurements_repo.py
Description:   Implementation and logic for test_measurements_repo.
Author:        Mai Tan Duc <ducmai.network@gmail.com>
Created:       2026-10-10
Version:       1.0.0
License:       MIT
==============================================================================
Usage:         python3 test_measurements_repo.py [options]
Notes:         Requires Python 3.8+
==============================================================================
"""

from datetime import datetime, timedelta, timezone

import pytest
from app.database import measurements_repo, targets_repo
from app.models.measurement import MeasurementCreate
from app.models.target import TargetCreate


@pytest.mark.asyncio
async def test_insert_and_list_measurements(db):
    target = await targets_repo.create_target(db, TargetCreate(name="DNS", host="8.8.8.8"))
    now = datetime.now(timezone.utc).isoformat()
    await measurements_repo.insert_measurement(
        db,
        MeasurementCreate(
            target_id=target.id,
            timestamp=now,
            latency_ms=15.0,
            packet_loss=0.0,
            jitter_ms=1.0,
            success=True,
        ),
    )
    rows = await measurements_repo.list_measurements(db, target_id=target.id)
    assert len(rows) == 1
    assert rows[0].latency_ms == 15.0
    assert rows[0].target_name == "DNS"


@pytest.mark.asyncio
async def test_latest_measurement_returns_most_recent(db):
    target = await targets_repo.create_target(db, TargetCreate(name="DNS", host="8.8.8.8"))
    base = datetime.now(timezone.utc)
    for i, latency in enumerate([10.0, 20.0, 30.0]):
        await measurements_repo.insert_measurement(
            db,
            MeasurementCreate(
                target_id=target.id,
                timestamp=(base + timedelta(seconds=i)).isoformat(),
                latency_ms=latency,
                packet_loss=0.0,
                jitter_ms=None,
                success=True,
            ),
        )
    latest = await measurements_repo.latest_measurement(db, target.id)
    assert latest is not None
    assert latest.latency_ms == 30.0


@pytest.mark.asyncio
async def test_recent_results_for_targets(db):
    target = await targets_repo.create_target(db, TargetCreate(name="DNS", host="8.8.8.8"))
    base = datetime.now(timezone.utc)
    for i, ok in enumerate([True, False, False]):
        await measurements_repo.insert_measurement(
            db,
            MeasurementCreate(
                target_id=target.id,
                timestamp=(base + timedelta(seconds=i)).isoformat(),
                latency_ms=10.0 if ok else None,
                packet_loss=0.0 if ok else 100.0,
                jitter_ms=None,
                success=ok,
            ),
        )
    results = await measurements_repo.recent_results_for_targets(db, [target.id], count=2)
    # newest-first: the last two inserts were both failures
    assert results[target.id] == [False, False]


@pytest.mark.asyncio
async def test_delete_older_than_retention(db):
    target = await targets_repo.create_target(db, TargetCreate(name="DNS", host="8.8.8.8"))
    old_ts = (datetime.now(timezone.utc) - timedelta(days=40)).isoformat()
    recent_ts = datetime.now(timezone.utc).isoformat()
    await measurements_repo.insert_measurement(
        db,
        MeasurementCreate(
            target_id=target.id,
            timestamp=old_ts,
            latency_ms=1.0,
            packet_loss=0.0,
            jitter_ms=None,
            success=True,
        ),
    )
    await measurements_repo.insert_measurement(
        db,
        MeasurementCreate(
            target_id=target.id,
            timestamp=recent_ts,
            latency_ms=1.0,
            packet_loss=0.0,
            jitter_ms=None,
            success=True,
        ),
    )
    deleted = await measurements_repo.delete_older_than(db, retention_days=30)
    assert deleted == 1
    remaining = await measurements_repo.list_measurements(db, target_id=target.id)
    assert len(remaining) == 1
    assert remaining[0].timestamp == recent_ts


@pytest.mark.asyncio
async def test_measurements_cascade_delete_with_target(db):
    target = await targets_repo.create_target(db, TargetCreate(name="DNS", host="8.8.8.8"))
    await measurements_repo.insert_measurement(
        db,
        MeasurementCreate(
            target_id=target.id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            latency_ms=1.0,
            packet_loss=0.0,
            jitter_ms=None,
            success=True,
        ),
    )
    await targets_repo.delete_target(db, target.id)
    remaining = await measurements_repo.list_measurements(db, target_id=target.id)
    assert remaining == []


@pytest.mark.asyncio
async def test_downsample_older_than_aggregates_and_preserves_on_recurring_runs(db):
    target = await targets_repo.create_target(db, TargetCreate(name="DNS", host="8.8.8.8"))
    old_time_1 = (datetime.now(timezone.utc) - timedelta(days=10)).replace(minute=5, second=0).isoformat()
    old_time_2 = (datetime.now(timezone.utc) - timedelta(days=10)).replace(minute=35, second=0).isoformat()
    recent_time = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()

    # Insert two measurements in the same hour bucket 10 days ago
    await measurements_repo.insert_measurement(
        db,
        MeasurementCreate(
            target_id=target.id,
            timestamp=old_time_1,
            latency_ms=20.0,
            packet_loss=0.0,
            jitter_ms=2.0,
            success=True,
        ),
    )
    await measurements_repo.insert_measurement(
        db,
        MeasurementCreate(
            target_id=target.id,
            timestamp=old_time_2,
            latency_ms=40.0,
            packet_loss=0.0,
            jitter_ms=4.0,
            success=True,
        ),
    )
    # Insert one recent measurement that should not be touched
    await measurements_repo.insert_measurement(
        db,
        MeasurementCreate(
            target_id=target.id,
            timestamp=recent_time,
            latency_ms=15.0,
            packet_loss=0.0,
            jitter_ms=1.0,
            success=True,
        ),
    )

    # First downsample run (7 days cutoff)
    count = await measurements_repo.downsample_older_than(db, days_old=7)
    assert count == 1

    rows = await measurements_repo.list_measurements(db, target_id=target.id)
    assert len(rows) == 2  # 1 recent + 1 downsampled
    downsampled = [r for r in rows if r.error == "Downsampled"]
    assert len(downsampled) == 1
    assert downsampled[0].latency_ms == 30.0  # avg of 20 and 40

    # Second downsample run (simulating recurring hourly job)
    count_second = await measurements_repo.downsample_older_than(db, days_old=7)
    assert count_second == 0  # No new raw rows to downsample

    rows_after = await measurements_repo.list_measurements(db, target_id=target.id)
    assert len(rows_after) == 2  # Downsampled row MUST NOT be deleted
    assert any(r.error == "Downsampled" for r in rows_after)
