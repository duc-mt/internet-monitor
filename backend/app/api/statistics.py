from __future__ import annotations

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_db
from app.models.status import StatisticsResponse
from app.services.statistics_service import RangeName, compute_statistics

router = APIRouter(prefix="/api/statistics", tags=["statistics"])


@router.get("", response_model=StatisticsResponse)
async def get_statistics(
    range: RangeName = "24h",
    start: str | None = None,
    end: str | None = None,
    target_id: int | None = None,
    db: aiosqlite.Connection = Depends(get_db),
):
    try:
        return await compute_statistics(
            db,
            range_name=range,
            start=start,
            end=end,
            target_id=target_id,  # type: ignore[arg-type]
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
