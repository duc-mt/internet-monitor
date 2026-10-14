"""
==============================================================================
Module Name:   quality_service.py
Description:   Source module quality_service.py.
Author:        Mai Tan Duc <ducmai.network@gmail.com>
Created:       2026-10-10
Version:       1.0.0
License:       MIT
==============================================================================
Usage:         python3 quality_service.py [options]
Notes:         Requires Python 3.8+
==============================================================================
"""

from __future__ import annotations

from app.models.settings import ClassificationThresholds, StabilityThresholds
from app.models.status import Quality, Stability


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


def classify_stability(iqr_ms: float | None, loss_pct: float | None, thresholds: StabilityThresholds) -> Stability:
    """
    STABILITY SCORE: how steady the link is, from the burst's IQR and loss -
    deliberately independent of how *low* the latency is (a 200 ms satellite
    link can be perfectly stable; a 10 ms one with spikes is not).

        excellent  loss == 0 and IQR <  excellent_iqr_ms
        good       loss <= good_loss_pct and IQR < good_iqr_ms
        fair       loss <= fair_loss_pct and IQR < fair_iqr_ms
        poor       anything worse
    """
    if iqr_ms is None or loss_pct is None:
        return "unknown"
    if loss_pct == 0 and iqr_ms < thresholds.excellent_iqr_ms:
        return "excellent"
    if loss_pct <= thresholds.good_loss_pct and iqr_ms < thresholds.good_iqr_ms:
        return "good"
    if loss_pct <= thresholds.fair_loss_pct and iqr_ms < thresholds.fair_iqr_ms:
        return "fair"
    return "poor"
