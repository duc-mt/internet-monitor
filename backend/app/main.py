from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

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
from app.services.notification_service import notifier_available

logging.basicConfig(
    level=os.environ.get("INTERNET_MONITOR_LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("internet_monitor")

# Set INTERNET_MONITOR_AUTOSTART=0 to boot the API without immediately
# spawning monitoring loops - used by the test suite and by `--no-autostart`.
AUTOSTART = os.environ.get("INTERNET_MONITOR_AUTOSTART", "1") != "0"


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
    await close_db()


app = FastAPI(title="Internet Monitor", version="1.0.0", lifespan=lifespan)

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
    assets_dir = FRONTEND_DIST_DIR / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_frontend(full_path: str):
        candidate = FRONTEND_DIST_DIR / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(FRONTEND_DIST_DIR / "index.html")
else:

    @app.get("/", include_in_schema=False)
    async def frontend_not_built():
        return {
            "message": "Frontend build not found. Run the frontend build (see README) or use the API directly.",
            "api_docs": "/docs",
        }
