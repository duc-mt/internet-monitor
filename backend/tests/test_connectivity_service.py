from __future__ import annotations

from datetime import datetime, timezone

import pytest
from app.database import measurements_repo, targets_repo
from app.models.measurement import MeasurementCreate
from app.models.settings import AppSettings
from app.models.target import TargetCreate
from app.services import connectivity_service, notification_service


@pytest.mark.asyncio
async def test_first_evaluation_does_not_notify(db, monkeypatch):
    sent = []

    async def fake_send(title, message, **kwargs):
        sent.append(title)

    monkeypatch.setattr(notification_service, "send", fake_send)
    target = await targets_repo.create_target(db, TargetCreate(name="DNS", host="1.1.1.1"))
    await measurements_repo.insert_measurement(
        db,
        MeasurementCreate(
            target_id=target.id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            latency_ms=10.0,
            packet_loss=0.0,
            jitter_ms=None,
            success=True,
        ),
    )
    online = await connectivity_service.evaluate(db, AppSettings())
    assert online is True
    assert sent == []


@pytest.mark.asyncio
async def test_transition_to_offline_notifies(db, monkeypatch):
    sent = []

    async def fake_send(title, message, **kwargs):
        sent.append(title)

    monkeypatch.setattr(notification_service, "send", fake_send)
    target = await targets_repo.create_target(db, TargetCreate(name="DNS", host="1.1.1.1"))
    now = datetime.now(timezone.utc)

    await measurements_repo.insert_measurement(
        db,
        MeasurementCreate(
            target_id=target.id,
            timestamp=now.isoformat(),
            latency_ms=10.0,
            packet_loss=0.0,
            jitter_ms=None,
            success=True,
        ),
    )
    await connectivity_service.evaluate(db, AppSettings())  # establishes baseline: online

    await measurements_repo.insert_measurement(
        db,
        MeasurementCreate(
            target_id=target.id,
            timestamp=now.isoformat(),
            latency_ms=None,
            packet_loss=100.0,
            jitter_ms=None,
            success=False,
        ),
    )
    online = await connectivity_service.evaluate(db, AppSettings())

    assert online is False
    assert any("lost" in t.lower() for t in sent)


@pytest.mark.asyncio
async def test_transition_back_online_notifies(db, monkeypatch):
    sent = []

    async def fake_send(title, message, **kwargs):
        sent.append(title)

    monkeypatch.setattr(notification_service, "send", fake_send)
    target = await targets_repo.create_target(db, TargetCreate(name="DNS", host="1.1.1.1"))
    now = datetime.now(timezone.utc)

    await measurements_repo.insert_measurement(
        db,
        MeasurementCreate(
            target_id=target.id,
            timestamp=now.isoformat(),
            latency_ms=None,
            packet_loss=100.0,
            jitter_ms=None,
            success=False,
        ),
    )
    await connectivity_service.evaluate(db, AppSettings())  # baseline: offline

    await measurements_repo.insert_measurement(
        db,
        MeasurementCreate(
            target_id=target.id,
            timestamp=now.isoformat(),
            latency_ms=8.0,
            packet_loss=0.0,
            jitter_ms=None,
            success=True,
        ),
    )
    online = await connectivity_service.evaluate(db, AppSettings())

    assert online is True
    assert any("restored" in t.lower() for t in sent)


@pytest.mark.asyncio
async def test_respects_disabled_notification_preference(db, monkeypatch):
    sent = []

    async def fake_send(title, message, **kwargs):
        sent.append(title)

    monkeypatch.setattr(notification_service, "send", fake_send)
    target = await targets_repo.create_target(db, TargetCreate(name="DNS", host="1.1.1.1"))
    now = datetime.now(timezone.utc)
    settings = AppSettings()
    settings.notifications.on_offline = False

    await measurements_repo.insert_measurement(
        db,
        MeasurementCreate(
            target_id=target.id,
            timestamp=now.isoformat(),
            latency_ms=10.0,
            packet_loss=0.0,
            jitter_ms=None,
            success=True,
        ),
    )
    await connectivity_service.evaluate(db, settings)

    await measurements_repo.insert_measurement(
        db,
        MeasurementCreate(
            target_id=target.id,
            timestamp=now.isoformat(),
            latency_ms=None,
            packet_loss=100.0,
            jitter_ms=None,
            success=False,
        ),
    )
    await connectivity_service.evaluate(db, settings)

    assert sent == []
