from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class MeasurementOut(BaseModel):
    id: int
    target_id: int
    target_name: Optional[str] = None
    timestamp: str
    latency_ms: Optional[float]
    packet_loss: float
    jitter_ms: Optional[float]
    success: bool
    error: Optional[str]
    network_name: Optional[str] = None

    model_config = {"from_attributes": True}


class MeasurementCreate(BaseModel):
    target_id: int
    timestamp: str
    latency_ms: Optional[float]
    packet_loss: float
    jitter_ms: Optional[float]
    success: bool
    error: Optional[str] = None
    network_name: Optional[str] = None
