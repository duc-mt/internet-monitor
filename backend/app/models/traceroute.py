"""
==============================================================================
Module Name:   traceroute.py
Description:   Source module traceroute.py.
Author:        Mai Tan Duc <ducmai.network@gmail.com>
Created:       2026-10-10
Version:       1.0.0
License:       MIT
==============================================================================
Usage:         python3 traceroute.py [options]
Notes:         Requires Python 3.8+
==============================================================================
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class TracerouteHopOut(BaseModel):
    hop: int
    address: str | None
    rtts_ms: list[float | None]
    avg_ms: float | None
    loss_pct: float
    # "private" = your LAN (hop 1 is normally the home router), "cgnat" = the
    # ISP's carrier-grade NAT range, "public" = the wider Internet.
    scope: Literal["private", "cgnat", "public", "unknown"]
    extra_addresses: list[str] = []


class TracerouteOut(BaseModel):
    target_id: int
    target_name: str
    host: str
    hops: list[TracerouteHopOut]
    raw: str
    # True when the time budget ran out; `hops` then holds what resolved so far.
    timed_out: bool
    elapsed_seconds: float
