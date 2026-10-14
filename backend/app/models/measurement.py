"""
==============================================================================
Module Name:   measurement.py
Description:   Source module measurement.py.
Author:        Mai Tan Duc <ducmai.network@gmail.com>
Created:       2026-10-10
Version:       1.0.0
License:       MIT
==============================================================================
Usage:         python3 measurement.py [options]
Notes:         Requires Python 3.8+
==============================================================================
"""

from __future__ import annotations

from pydantic import BaseModel


class BurstFields(BaseModel):
    """
    Burst Probing summary of one check, in milliseconds (loss is the existing
    ``packet_loss`` percentage). Every field is None on rows recorded before
    the upgrade, or when every probe in the burst was lost.
    """

    median_ms: float | None = None
    p25_ms: float | None = None
    p75_ms: float | None = None
    p95_ms: float | None = None
    min_ms: float | None = None
    max_ms: float | None = None
    iqr_ms: float | None = None
    jitter_rfc3550: float | None = None
    packet_count: int | None = None


class MeasurementOut(BurstFields):
    id: int
    target_id: int
    target_name: str | None = None
    timestamp: str
    latency_ms: float | None
    packet_loss: float
    jitter_ms: float | None
    success: bool
    error: str | None
    network_name: str | None = None

    model_config = {"from_attributes": True}


class MeasurementCreate(BurstFields):
    target_id: int
    timestamp: str
    latency_ms: float | None
    packet_loss: float
    jitter_ms: float | None
    success: bool
    error: str | None = None
    network_name: str | None = None
