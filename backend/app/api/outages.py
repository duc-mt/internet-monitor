from __future__ import annotations

from typing import Optional

import aiosqlite
from fastapi import APIRouter, Depends

from app.api.deps import get_db
from app.database import outages_repo
from app.models.outage import OutageOut

router = APIRouter(prefix="/api/outages", tags=["outages"])


@router.get("", response_model=list[OutageOut])
async def list_outages(
    start: Optional[str] = None,
    end: Optional[str] = None,
    limit: int = 200,
    db: aiosqlite.Connection = Depends(get_db),
):
    return await outages_repo.list_outages(db, start=start, end=end, limit=limit)
