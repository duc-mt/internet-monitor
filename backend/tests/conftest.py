"""
Shared test fixtures.

Two ground rules for this whole suite (per the project brief):
  1. No test may depend on real Internet connectivity.
  2. No test may talk to a real network target - the pinger's subprocess
     and socket calls are monkeypatched wherever a test exercises code
     that would otherwise reach out.

INTERNET_MONITOR_AUTOSTART is forced to "0" before app.main is ever
imported so the FastAPI lifespan never spawns real monitoring loops
against the live internet during API tests.
"""

from __future__ import annotations

import os

os.environ["INTERNET_MONITOR_AUTOSTART"] = "0"

from pathlib import Path

import pytest
import pytest_asyncio
from app.database import connection as db_connection
from app.monitoring import network_info
from app.monitoring import scheduler as monitoring_scheduler
from app.monitoring.pinger import PingBatchResult
from app.services import (
    connectivity_service,
    notification_service,
    outage_service,
    settings_service,
    sleep_service,
)


async def _fake_run_check(*, host, protocol, port, count, timeout):
    """Stand-in for app.monitoring.pinger.run_check so that if a test starts
    the real MonitoringManager, it never actually touches the network."""
    return PingBatchResult(method=protocol, attempted=count, succeeded=count, latencies=[1.0] * count)


@pytest_asyncio.fixture
async def db(tmp_path: Path):
    """A fresh, isolated SQLite database for a single test."""
    db_path = tmp_path / "test.db"
    conn = await db_connection.init_db(db_path)
    settings_service.invalidate_cache()
    connectivity_service.reset_state()
    outage_service.reset_state()
    notification_service.reset_cooldowns()
    sleep_service.reset_state()
    network_info.reset_cache()
    yield conn
    await db_connection.close_db()


@pytest.fixture
def client(tmp_path: Path, monkeypatch):
    """A FastAPI TestClient wired to its own temp database, with monitoring
    loops disabled (AUTOSTART=0 set at module import time above)."""
    monkeypatch.setattr(db_connection, "DATABASE_PATH", tmp_path / "client.db")
    monkeypatch.setattr(monitoring_scheduler, "run_check", _fake_run_check)
    settings_service.invalidate_cache()
    connectivity_service.reset_state()
    outage_service.reset_state()
    notification_service.reset_cooldowns()
    sleep_service.reset_state()
    network_info.reset_cache()

    from app.main import app
    from fastapi.testclient import TestClient

    with TestClient(app) as test_client:
        yield test_client
    # Exiting the context above already ran the app's shutdown (manager.stop()
    # + close_db()) via the lifespan handler.
