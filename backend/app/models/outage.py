"""
==============================================================================
Module Name:   outage.py
Description:   Source module outage.py.
Author:        Mai Tan Duc <ducmai.network@gmail.com>
Created:       2026-10-10
Version:       1.0.0
License:       MIT
==============================================================================
Usage:         python3 outage.py [options]
Notes:         Requires Python 3.8+
==============================================================================
"""

from __future__ import annotations

from pydantic import BaseModel


class OutageOut(BaseModel):
    id: int
    started_at: str
    ended_at: str | None
    duration_seconds: float | None
    reason: str | None
    affected_targets: list[str]
    failed_checks: int
    is_active: bool

    model_config = {"from_attributes": True}
