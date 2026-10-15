"""
==============================================================================
Module Name:   conftest.py
Description:   Source module conftest.py.
Author:        Mai Tan Duc <ducmai.network@gmail.com>
Created:       2026-10-10
Version:       1.0.0
License:       MIT
==============================================================================
Usage:         python3 conftest.py [options]
Notes:         Requires Python 3.8+
==============================================================================
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
from app.monitoring.burst_stats import BurstMetric, compute_burst_metric
from app.services import (
    connectivity_service,
    notification_service,
    outage_service,
    settings_service,
    sleep_service,
    status_service,
)


async def _fake_run_burst(*, host, protocol, port, count, interval_ms, timeout) -> BurstMetric:
    """Stand-in for app.monitoring.burst_prober.run_burst so that if a test starts
    the real MonitoringManager, it never actually touches the network."""
    return compute_burst_metric([1.0] * count, method=protocol)


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
    status_service.reset_status_cache()
    yield conn
    await db_connection.close_db()


@pytest.fixture
def client(tmp_path: Path, monkeypatch):
    """A FastAPI TestClient wired to its own temp database, with monitoring
    loops disabled (AUTOSTART=0 set at module import time above)."""
    monkeypatch.setattr(db_connection, "DATABASE_PATH", tmp_path / "client.db")
    monkeypatch.setattr(monitoring_scheduler, "run_burst", _fake_run_burst)
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
