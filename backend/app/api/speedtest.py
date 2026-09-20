from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.speedtest_service import run_speedtest

router = APIRouter(prefix="/api/speedtest", tags=["speedtest"])


class SpeedtestResponse(BaseModel):
    download_mbps: float
    bytes_downloaded: int
    elapsed_seconds: float
    server: str


@router.post("", response_model=SpeedtestResponse)
async def trigger_speedtest():
    """
    Manual only, by design - see app/services/speedtest_service.py. There is
    no scheduled/background variant of this endpoint anywhere in the app.
    """
    try:
        result = await run_speedtest()
    except Exception as exc:  # network error, timeout, non-2xx, etc.
        raise HTTPException(status_code=502, detail=f"Speed test failed: {exc}")
    return SpeedtestResponse(**result.__dict__)
