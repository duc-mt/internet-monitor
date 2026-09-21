from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel

Quality = Literal["excellent", "good", "fair", "poor", "offline", "unknown"]


class TargetStatus(BaseModel):
    target_id: int
    name: str
    host: str
    reachable: bool
    latency_ms: Optional[float]
    packet_loss: Optional[float]
    last_checked: Optional[str]


class StatusResponse(BaseModel):
    online: bool
    quality: Quality
    latency_ms: Optional[float]
    packet_loss: Optional[float]
    jitter_ms: Optional[float]
    network_name: Optional[str] = None
    monitoring_uptime_seconds: float
    uptime_pct_24h: Optional[float] = None
    targets_reachable: int
    targets_total: int
    targets: List[TargetStatus]
    active_outage: bool
    monitoring_running: bool


class StatisticsResponse(BaseModel):
    range_start: str
    range_end: str
    target_id: Optional[int]
    sample_count: int
    avg_latency_ms: Optional[float]
    min_latency_ms: Optional[float]
    max_latency_ms: Optional[float]
    median_latency_ms: Optional[float]
    p95_latency_ms: Optional[float]
    packet_loss_pct: Optional[float]
    avg_jitter_ms: Optional[float]
    uptime_pct: Optional[float]
    outage_count: int
    longest_outage_seconds: Optional[float]
    monitoring_duration_seconds: float
