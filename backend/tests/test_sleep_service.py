from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.database import outages_repo
from app.services import sleep_service


@pytest.mark.asyncio
async def test_first_tick_ever_does_not_insert_anything(db):
    # No previous tick to compare against - nothing to detect yet.
    await sleep_service.check_gap(db, threshold_seconds=60)
    assert await outages_repo.list_outages(db) == []


@pytest.mark.asyncio
async def test_small_gap_is_normal_and_ignored(db):
    sleep_service._last_tick_wall = datetime.now(timezone.utc) - timedelta(seconds=5)
    await sleep_service.check_gap(db, threshold_seconds=60)
    assert await outages_repo.list_outages(db) == []


@pytest.mark.asyncio
async def test_large_gap_is_recorded_as_system_sleep(db):
    sleep_service._last_tick_wall = datetime.now(timezone.utc) - timedelta(seconds=120)
    await sleep_service.check_gap(db, threshold_seconds=60)

    outages = await outages_repo.list_outages(db)
    assert len(outages) == 1
    assert outages[0].reason == "system_sleep"
    assert outages[0].duration_seconds >= 119
    assert outages[0].is_active is False  # both start and end are known immediately


@pytest.mark.asyncio
async def test_does_not_duplicate_on_the_next_call(db):
    sleep_service._last_tick_wall = datetime.now(timezone.utc) - timedelta(seconds=120)
    await sleep_service.check_gap(db, threshold_seconds=60)
    await sleep_service.check_gap(db, threshold_seconds=60)  # gap since the recorded tick is ~0s
    assert len(await outages_repo.list_outages(db)) == 1


@pytest.mark.asyncio
async def test_sleep_gap_excluded_from_outage_count_and_longest(db):
    sleep_service._last_tick_wall = datetime.now(timezone.utc) - timedelta(hours=8)
    await sleep_service.check_gap(db, threshold_seconds=60)

    now = datetime.now(timezone.utc)
    stats = await outages_repo.outage_stats_in_range(
        db, start=(now - timedelta(hours=24)).isoformat(), end=(now + timedelta(minutes=1)).isoformat()
    )
    # Without the reason != 'system_sleep' filter, this would show 1 outage
    # lasting ~8 hours - exactly the false signal this feature exists to avoid.
    assert stats["outage_count"] == 0
    assert stats["longest"] is None


@pytest.mark.asyncio
async def test_downtime_and_sleep_seconds_are_kept_separate(db):
    now = datetime.now(timezone.utc)

    real_outage = await outages_repo.start_outage(
        db, reason="all monitored external targets unreachable", affected_targets=["DNS"], failed_checks=3
    )
    await outages_repo.end_active_outage(db)

    sleep_service._last_tick_wall = now - timedelta(seconds=200)
    await sleep_service.check_gap(db, threshold_seconds=60)

    real_downtime, sleep_seconds = await outages_repo.downtime_and_sleep_seconds_in_range(
        db, start=(now - timedelta(hours=1)).isoformat(), end=(now + timedelta(hours=1)).isoformat()
    )
    assert sleep_seconds >= 199
    assert real_downtime < 5  # the real outage was opened and closed almost instantly
    assert real_outage.reason != "system_sleep"
