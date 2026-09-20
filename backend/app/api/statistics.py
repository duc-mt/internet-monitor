from __future__ import annotations

from typing import Optional

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_db
from app.models.status import StatisticsResponse
from app.services import statistics_service

router = APIRouter(prefix="/api/statistics", tags=["statistics"])


@router.get("", response_model=StatisticsResponse)
async def get_statistics(
    range: str = "24h",
    start: Optional[str] = None,
    end: Optional[str] = None,
    target_id: Optional[int] = None,
    db: aiosqlite.Connection = Depends(get_db),
):
    try:
        return await statistics_service.compute_statistics(
            db, range_name=range, start=start, end=end, target_id=target_id  # type: ignore[arg-type]
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
