from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.database import measurements_repo, outages_repo, targets_repo
from app.models.measurement import MeasurementCreate
from app.models.settings import AppSettings
from app.models.target import TargetCreate
from app.services import notification_service, outage_service


async def _record(db, target_id: int, success: bool, when: datetime):
    await measurements_repo.insert_measurement(db, MeasurementCreate(
        target_id=target_id, timestamp=when.isoformat(),
        latency_ms=10.0 if success else None,
        packet_loss=0.0 if success else 100.0,
        jitter_ms=None, success=success,
    ))


@pytest.mark.asyncio
async def test_outage_created_when_all_external_targets_fail(db):
    settings = AppSettings(outage_threshold_checks=2)
    gateway = await targets_repo.create_target(db, TargetCreate(name="GW", host="192.168.1.1", is_gateway=True))
    dns1 = await targets_repo.create_target(db, TargetCreate(name="DNS1", host="1.1.1.1"))
    dns2 = await targets_repo.create_target(db, TargetCreate(name="DNS2", host="8.8.8.8"))

    now = datetime.now(timezone.utc)
    # Gateway stays healthy throughout - only external targets fail.
    await _record(db, gateway.id, True, now)
    for i in range(2):
        await _record(db, dns1.id, False, now + timedelta(seconds=i))
        await _record(db, dns2.id, False, now + timedelta(seconds=i))

    await outage_service.evaluate(db, settings)

    active = await outages_repo.get_active_outage(db)
    assert active is not None
    assert set(active.affected_targets) == {"DNS1", "DNS2"}


@pytest.mark.asyncio
async def test_no_outage_when_only_gateway_fails(db):
    settings = AppSettings(outage_threshold_checks=2)
    gateway = await targets_repo.create_target(db, TargetCreate(name="GW", host="192.168.1.1", is_gateway=True))
    dns1 = await targets_repo.create_target(db, TargetCreate(name="DNS1", host="1.1.1.1"))

    now = datetime.now(timezone.utc)
    for i in range(2):
        await _record(db, gateway.id, False, now + timedelta(seconds=i))
    await _record(db, dns1.id, True, now)

    await outage_service.evaluate(db, settings)

    assert await outages_repo.get_active_outage(db) is None


@pytest.mark.asyncio
async def test_outage_closes_when_a_target_recovers(db):
    settings = AppSettings(outage_threshold_checks=2)
    dns1 = await targets_repo.create_target(db, TargetCreate(name="DNS1", host="1.1.1.1"))

    now = datetime.now(timezone.utc)
    for i in range(2):
        await _record(db, dns1.id, False, now + timedelta(seconds=i))
    await outage_service.evaluate(db, settings)
    assert await outages_repo.get_active_outage(db) is not None

    await _record(db, dns1.id, True, now + timedelta(seconds=5))
    await outage_service.evaluate(db, settings)
    assert await outages_repo.get_active_outage(db) is None

    outages = await outages_repo.list_outages(db)
    assert outages[0].duration_seconds is not None


@pytest.mark.asyncio
async def test_outage_duration_notification_fires_once(db, monkeypatch):
    sent = []

    async def fake_send(title, message, **kwargs):
        sent.append((title, kwargs.get("key")))

    monkeypatch.setattr(notification_service, "send", fake_send)

    settings = AppSettings(outage_threshold_checks=1, outage_notify_min_duration_seconds=0)
    dns1 = await targets_repo.create_target(db, TargetCreate(name="DNS1", host="1.1.1.1"))
    now = datetime.now(timezone.utc)
    await _record(db, dns1.id, False, now)

    await outage_service.evaluate(db, settings)
    await outage_service.evaluate(db, settings)  # second pass should not re-notify

    duration_notifications = [s for s in sent if "outage_duration" in (s[1] or "")]
    assert len(duration_notifications) == 1
