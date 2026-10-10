from __future__ import annotations

"""
==============================================================================
Module Name:   health.py
Description:   Implementation and logic for health.
Author:        Mai Tan Duc <ducmai.network@gmail.com>
Created:       2026-10-10
Version:       1.0.0
License:       MIT
==============================================================================
Usage:         python3 health.py [options]
Notes:         Requires Python 3.8+
==============================================================================
"""

from fastapi import APIRouter

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
async def health():
    return {"status": "ok"}
