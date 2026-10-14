"""
==============================================================================
Module Name:   burst_stats.py
Description:   Pure in-memory statistics for one burst of RTT samples.
Author:        Mai Tan Duc <ducmai.network@gmail.com>
Created:       2026-10-14
Version:       1.0.0
License:       MIT
==============================================================================
Usage:         from app.monitoring.burst_stats import compute_burst_metric
Notes:         No I/O, no clocks: everything here is deterministic and unit-tested.
==============================================================================
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass


def percentile(sorted_values: Sequence[float], pct: float) -> float:
    """
    Percentile with linear interpolation between closest ranks (the "type 7"
    definition used by NumPy's default and Excel's PERCENTILE.INC). ``pct`` is
    0-100 and ``sorted_values`` must be non-empty and ascending.

    Example: [10, 20, 30, 40] -> p25 = 17.5, p50 = 25, p75 = 32.5.
    """
    n = len(sorted_values)
    if n == 0:
        raise ValueError("percentile() of an empty sequence")
    if n == 1:
        return float(sorted_values[0])
    index = (pct / 100) * (n - 1)
    lower = int(index)
    upper = min(lower + 1, n - 1)
    weight = index - lower
    return sorted_values[lower] * (1 - weight) + sorted_values[upper] * weight


def rfc3550_jitter(rtts_in_arrival_order: Sequence[float]) -> float | None:
    """
    Interarrival jitter as defined in RFC 3550 section 6.4.1, fed with RTTs:

        D(i-1, i) = |(R_i - S_i) - (R_{i-1} - S_{i-1})| = |RTT_i - RTT_{i-1}|
        J(i)      = J(i-1) + (|D(i-1, i)| - J(i-1)) / 16        J(0) = 0

    Only successfully received probes take part (a lost one has no transit time),
    in the order they were sent. Needs at least two samples, else None.

    Note the 1/16 gain: after the 10-20 samples of a burst the estimate has only
    partly converged from its zero start, so it reads *lower* than the plain mean
    of |D|. That is what the RFC defines; it is a per-burst smoothed indicator.
    """
    if len(rtts_in_arrival_order) < 2:
        return None
    jitter = 0.0
    for previous, current in zip(rtts_in_arrival_order, rtts_in_arrival_order[1:]):
        jitter += (abs(current - previous) - jitter) / 16
    return jitter


@dataclass(frozen=True)
class BurstMetric:
    """
    The reduced result of one burst. All RTT fields are milliseconds, measured
    with microsecond resolution and rounded to 3 decimals; they are None when no
    probe was answered. ``packet_count`` is how many probes were *sent*.
    """

    method: str  # "icmp" | "tcp"
    packet_count: int
    received: int
    loss_percent: float
    min_rtt: float | None = None
    max_rtt: float | None = None
    median_rtt: float | None = None  # p50 - the "base latency"
    p25_rtt: float | None = None
    p75_rtt: float | None = None
    iqr_rtt: float | None = None  # p75 - p25: the core variation
    p95_rtt: float | None = None  # tail latency within the burst
    jitter_rfc3550: float | None = None
    error: str | None = None

    @property
    def lost(self) -> int:
        return self.packet_count - self.received

    @property
    def success(self) -> bool:
        return self.received > 0


def _ms(value: float) -> float:
    return round(value, 3)


def compute_burst_metric(rtts_ms: Sequence[float | None], *, method: str, error: str | None = None) -> BurstMetric:
    """
    Reduces one burst to a BurstMetric. ``rtts_ms`` has one entry per probe
    *sent*, in send order: the RTT in ms, or None for a probe that was lost.
    The raw list is not kept - callers drop it as soon as this returns.
    """
    sent = len(rtts_ms)
    if sent == 0:
        raise ValueError("a burst needs at least one probe")
    answered = [r for r in rtts_ms if r is not None]
    received = len(answered)
    loss = round((sent - received) / sent * 100, 2)

    if received == 0:
        return BurstMetric(method=method, packet_count=sent, received=0, loss_percent=loss, error=error or "no reply")

    ordered = sorted(answered)
    p25 = percentile(ordered, 25)
    p75 = percentile(ordered, 75)
    jitter = rfc3550_jitter(answered)
    return BurstMetric(
        method=method,
        packet_count=sent,
        received=received,
        loss_percent=loss,
        min_rtt=_ms(ordered[0]),
        max_rtt=_ms(ordered[-1]),
        median_rtt=_ms(percentile(ordered, 50)),
        p25_rtt=_ms(p25),
        p75_rtt=_ms(p75),
        iqr_rtt=_ms(p75 - p25),
        p95_rtt=_ms(percentile(ordered, 95)),
        jitter_rfc3550=_ms(jitter) if jitter is not None else None,
        error=None,
    )
