from __future__ import annotations
"""
==============================================================================
Module Name:   monitoring.py
Description:   Implementation and logic for monitoring.
Author:        Mai Tan Duc <ducmai.network@gmail.com>
Created:       2026-10-10
Version:       1.0.0
License:       MIT
==============================================================================
Usage:         python3 monitoring.py [options]
Notes:         Requires Python 3.8+
==============================================================================
"""

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
