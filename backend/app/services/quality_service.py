from __future__ import annotations

from app.models.settings import ClassificationThresholds
from app.models.status import Quality


def classify(latency_ms: float | None, packet_loss_pct: float | None, thresholds: ClassificationThresholds) -> Quality:
    # Caller is responsible for reporting "offline" based on overall
    # reachability; this function only classifies quality when we have an
    # actual latency reading to classify.
    if latency_ms is None or packet_loss_pct is None:
        return "unknown"
    if latency_ms < thresholds.excellent_latency_ms and packet_loss_pct < thresholds.excellent_packet_loss_pct:
        return "excellent"
    if latency_ms < thresholds.good_latency_ms and packet_loss_pct < thresholds.good_packet_loss_pct:
        return "good"
    if latency_ms < thresholds.fair_latency_ms or packet_loss_pct < thresholds.fair_packet_loss_pct:
        return "fair"
    return "poor"
