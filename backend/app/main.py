"""
==============================================================================
Module Name:   main.py
Description:   Source module main.py.
Author:        Mai Tan Duc <ducmai.network@gmail.com>
Created:       2026-10-10
Version:       1.0.0
License:       MIT
==============================================================================
Usage:         python3 main.py [options]
Notes:         Requires Python 3.8+
==============================================================================
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.gzip import GZipMiddleware

from app.api import (
    export,
    health,
    measurements,
    monitoring,
    outages,
    settings,
    speedtest,
    statistics,
    status,
    targets,
)
from app.config import DEV_CORS_ORIGINS, FRONTEND_DIST_DIR
from app.database.connection import close_db, init_db
from app.database.targets_repo import seed_default_targets
from app.monitoring.scheduler import manager
from app.services import notification_service
from app.services.notification_service import notifier_available
from app.spa import mount_frontend

logging.basicConfig(
    level=os.environ.get("INTERNET_MONITOR_LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("internet_monitor")

# Set INTERNET_MONITOR_AUTOSTART=0 to boot the API without immediately
# spawning monitoring loops - used by the test suite and by `--no-autostart`.
AUTOSTART = os.environ.get("INTERNET_MONITOR_AUTOSTART", "1") != "0"

# Upper bound on how long shutdown waits for in-flight webhook deliveries
# (each one has its own 10s HTTP timeout) so a dead endpoint cannot hang exit.
_WEBHOOK_FLUSH_TIMEOUT_SECONDS = 5.0


@asynccontextmanager
async def lifespan(app: FastAPI):
    conn = await init_db()
    await seed_default_targets(conn)
    if not notifier_available():
        logger.info("No desktop notification tool found - notifications will be logged only")
    if AUTOSTART:
        await manager.start(conn)
    yield
    await manager.stop()
    # Webhook alerts are fired as background tasks; the last "offline" alert
    # right before a shutdown would otherwise be silently dropped.
    with contextlib.suppress(asyncio.TimeoutError):
        await asyncio.wait_for(notification_service.flush_webhooks(), timeout=_WEBHOOK_FLUSH_TIMEOUT_SECONDS)
    await close_db()


app = FastAPI(title="Internet Monitor", version="1.0.0", lifespan=lifespan)

app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=DEV_CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

for router in (
    health.router,
    status.router,
    targets.router,
    measurements.router,
    statistics.router,
    outages.router,
    settings.router,
    monitoring.router,
    export.router,
    speedtest.router,
):
    app.include_router(router)

if FRONTEND_DIST_DIR.is_dir():
    mount_frontend(app, FRONTEND_DIST_DIR)
else:

    @app.get("/", include_in_schema=False)
    async def frontend_not_built():
        return {
            "message": "Frontend build not found. Run the frontend build (see README) or use the API directly.",
            "api_docs": "/docs",
        }
