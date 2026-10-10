from __future__ import annotations
"""
==============================================================================
Module Name:   status.py
Description:   Implementation and logic for status.
Author:        Mai Tan Duc <ducmai.network@gmail.com>
Created:       2026-10-10
Version:       1.0.0
License:       MIT
==============================================================================
Usage:         python3 status.py [options]
Notes:         Requires Python 3.8+
==============================================================================
"""

import aiosqlite
from fastapi import APIRouter, Depends

from app.api.deps import get_db
from app.models.status import StatusResponse
from app.monitoring.scheduler import manager
from app.services.status_service import compute_status

router = APIRouter(prefix="/api", tags=["status"])


@router.get("/status", response_model=StatusResponse)
async def get_status(db: aiosqlite.Connection = Depends(get_db)):
    return await compute_status(db, monitoring_started_at=manager.started_at, monitoring_running=manager.running)
