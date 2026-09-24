from __future__ import annotations

import aiosqlite
from fastapi import APIRouter, Depends

from app.api.deps import get_db
from app.database import outages_repo
from app.models.outage import OutageOut

router = APIRouter(prefix="/api/outages", tags=["outages"])


@router.get("", response_model=list[OutageOut])
async def list_outages(
    start: str | None = None,
    end: str | None = None,
    limit: int = 200,
    db: aiosqlite.Connection = Depends(get_db),
):
    return await outages_repo.list_outages(db, start=start, end=end, limit=limit)
