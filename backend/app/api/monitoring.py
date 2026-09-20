from __future__ import annotations

import aiosqlite
from fastapi import APIRouter, Depends

from app.api.deps import get_db
from app.monitoring.scheduler import manager

router = APIRouter(prefix="/api/monitoring", tags=["monitoring"])


@router.post("/start")
async def start_monitoring(db: aiosqlite.Connection = Depends(get_db)):
    await manager.start(db)
    return {"running": manager.running}


@router.post("/stop")
async def stop_monitoring():
    await manager.stop()
    return {"running": manager.running}
