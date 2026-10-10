"""
==============================================================================
Module Name:   speedtest.py
Description:   Source module speedtest.py.
Author:        Mai Tan Duc <ducmai.network@gmail.com>
Created:       2026-10-10
Version:       1.0.0
License:       MIT
==============================================================================
Usage:         python3 speedtest.py [options]
Notes:         Requires Python 3.8+
==============================================================================
"""

import asyncio

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.speedtest_service import run_speedtest

router = APIRouter(prefix="/api/speedtest", tags=["speedtest"])

_speedtest_lock = asyncio.Lock()


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
    if _speedtest_lock.locked():
        raise HTTPException(status_code=409, detail="Speed test already in progress")

    async with _speedtest_lock:
        try:
            result = await run_speedtest()
        except Exception as exc:  # network error, timeout, non-2xx, etc.
            raise HTTPException(status_code=502, detail=f"Speed test failed: {exc}")
        return SpeedtestResponse(**result.__dict__)
