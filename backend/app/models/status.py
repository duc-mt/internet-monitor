from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

Quality = Literal["excellent", "good", "fair", "poor", "offline", "unknown"]


class TargetStatus(BaseModel):
    target_id: int
    name: str
    host: str
    reachable: bool
    latency_ms: float | None
    packet_loss: float | None
    last_checked: str | None


class StatusResponse(BaseModel):
    online: bool
    quality: Quality
    latency_ms: float | None
    packet_loss: float | None
    jitter_ms: float | None
    network_name: str | None = None
    monitoring_uptime_seconds: float
    uptime_pct_24h: float | None = None
    targets_reachable: int
    targets_total: int
    targets: list[TargetStatus]
    active_outage: bool
    monitoring_running: bool


class StatisticsResponse(BaseModel):
    range_start: str
    range_end: str
    target_id: int | None
    sample_count: int
    avg_latency_ms: float | None
    min_latency_ms: float | None
    max_latency_ms: float | None
    median_latency_ms: float | None
    p95_latency_ms: float | None
    packet_loss_pct: float | None
    avg_jitter_ms: float | None
    uptime_pct: float | None
    outage_count: int
    longest_outage_seconds: float | None
    monitoring_duration_seconds: float
