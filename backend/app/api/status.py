from __future__ import annotations

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
