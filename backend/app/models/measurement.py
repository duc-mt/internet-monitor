from __future__ import annotations
"""
==============================================================================
Module Name:   measurement.py
Description:   Implementation and logic for measurement.
Author:        Mai Tan Duc <ducmai.network@gmail.com>
Created:       2026-10-10
Version:       1.0.0
License:       MIT
==============================================================================
Usage:         python3 measurement.py [options]
Notes:         Requires Python 3.8+
==============================================================================
"""

from pydantic import BaseModel


class MeasurementOut(BaseModel):
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


class MeasurementCreate(BaseModel):
    target_id: int
    timestamp: str
    latency_ms: float | None
    packet_loss: float
    jitter_ms: float | None
    success: bool
    error: str | None = None
    network_name: str | None = None
