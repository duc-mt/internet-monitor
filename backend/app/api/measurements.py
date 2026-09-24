from __future__ import annotations

import aiosqlite
from fastapi import APIRouter, Depends, Query

from app.api.deps import get_db
from app.database import measurements_repo
from app.models.measurement import MeasurementOut

router = APIRouter(prefix="/api/measurements", tags=["measurements"])


@router.get("", response_model=list[MeasurementOut])
async def list_measurements(
    target_id: int | None = None,
    start: str | None = None,
    end: str | None = None,
    limit: int = Query(default=1000, ge=1, le=20000),
    db: aiosqlite.Connection = Depends(get_db),
):
    return await measurements_repo.list_measurements(db, target_id=target_id, start=start, end=end, limit=limit)
