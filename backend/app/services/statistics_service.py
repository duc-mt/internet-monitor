"""
==============================================================================
Module Name:   statistics_service.py
Description:   Source module statistics_service.py.
Author:        Mai Tan Duc <ducmai.network@gmail.com>
Created:       2026-10-10
Version:       1.0.0
License:       MIT
==============================================================================
Usage:         python3 statistics_service.py [options]
Notes:         Requires Python 3.8+
==============================================================================
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Literal

import aiosqlite

from app.database import measurements_repo, outages_repo
from app.models.status import StatisticsResponse
from app.monitoring.burst_stats import percentile

RangeName = Literal["1h", "24h", "7d", "30d", "custom"]

_RANGE_DELTAS = {
    "1h": timedelta(hours=1),
    "24h": timedelta(hours=24),
    "7d": timedelta(days=7),
    "30d": timedelta(days=30),
}


def resolve_range(range_name: RangeName, start: str | None, end: str | None) -> tuple[datetime, datetime]:
    now = datetime.now(timezone.utc)
    if range_name == "custom":
        if not start or not end:
            raise ValueError("start and end are required when range=custom")
        range_start = datetime.fromisoformat(start)
        range_end = datetime.fromisoformat(end)
        if range_start.tzinfo is None:
            range_start = range_start.replace(tzinfo=timezone.utc)
        if range_end.tzinfo is None:
            range_end = range_end.replace(tzinfo=timezone.utc)
        if range_start >= range_end:
            raise ValueError("start must be before end")
        return range_start, range_end
    delta = _RANGE_DELTAS.get(range_name)
    if delta is None:
        raise ValueError(f"unknown range {range_name!r}")
    return now - delta, now


def weighted_percentile(pairs: list[tuple[float, float]], pct: float) -> float:
    """
    Nearest-rank percentile of (value, weight) pairs: the smallest value whose
    cumulative weight reaches pct% of the total. Used only for ranges that
    reach into the hourly tier, where one value stands for many checks.
    """
    ordered = sorted(pairs)
    total = sum(w for _, w in ordered)
    threshold = total * pct / 100
    running = 0.0
    for value, weight in ordered:
        running += weight
        if running >= threshold:
            return value
    return ordered[-1][0]


def _weighted_mean(pairs: list[tuple[float, float]]) -> float | None:
    total = sum(w for _, w in pairs)
    return sum(v * w for v, w in pairs) / total if total > 0 else None


def _seconds_between(first: str | None, last: str | None) -> float:
    if not first or not last:
        return 0.0
    try:
        return max(0.0, (datetime.fromisoformat(last) - datetime.fromisoformat(first)).total_seconds())
    except ValueError:
        return 0.0


def uptime_percentage(duration_seconds: float, downtime_seconds: float, sleep_seconds: float) -> float | None:
    """
    Uptime% is computed over the time we actually observed (data coverage
    minus detected sleep gaps), not the raw wall-clock size of the requested
    range - a fresh install asked about "last 30 days" should not be penalized
    (or flattered) for the days before it existed, and a laptop that slept for
    8 of the last 24 hours shouldn't have those 8 hours silently counted as
    either "up" or "down" - excluded from both sides of the ratio, same as
    it's excluded from the outage log.
    """
    effective_seconds = max(0.0, duration_seconds - sleep_seconds)
    if effective_seconds <= 0:
        return None
    return round(max(0.0, 100 * (1 - downtime_seconds / effective_seconds)), 2)


async def compute_uptime_pct(
    conn: aiosqlite.Connection, *, window: timedelta = timedelta(hours=24), target_id: int | None = None
) -> float | None:
    """
    The headline "uptime over the last <window>" figure, for the dashboard's
    every-few-seconds /api/status poll. Same maths as compute_statistics()'s
    uptime_pct, but it never loads or sorts the latency samples: two indexed
    MIN/MAX lookups for the covered time plus the (tiny) outages table.
    """
    now = datetime.now(timezone.utc)
    start_iso, end_iso = (now - window).isoformat(), now.isoformat()
    first, last = await measurements_repo.coverage_bounds(conn, target_id=target_id, start=start_iso, end=end_iso)
    downtime, sleep = await outages_repo.downtime_and_sleep_seconds_in_range(conn, start=start_iso, end=end_iso)
    return uptime_percentage(_seconds_between(first, last), downtime, sleep)


async def compute_statistics(
    conn: aiosqlite.Connection,
    *,
    range_name: RangeName,
    start: str | None = None,
    end: str | None = None,
    target_id: int | None = None,
) -> StatisticsResponse:
    range_start, range_end = resolve_range(range_name, start, end)
    start_iso, end_iso = range_start.isoformat(), range_end.isoformat()

    points = await measurements_repo.latency_points_in_range(conn, target_id=target_id, start=start_iso, end=end_iso)
    agg = await measurements_repo.aggregate_in_range(conn, target_id=target_id, start=start_iso, end=end_iso)
    hourly = await measurements_repo.hourly_rows_in_range(conn, target_id=target_id, start=start_iso, end=end_iso)
    outage_agg = await outages_repo.outage_stats_in_range(conn, start=start_iso, end=end_iso)
    real_downtime_seconds, sleep_seconds = await outages_repo.downtime_and_sleep_seconds_in_range(
        conn, start=start_iso, end=end_iso
    )

    raw_n = agg.get("sample_count") or 0
    sample_count = raw_n + sum(h["sample_count"] for h in hourly)

    # Latency series, one value per check: the median RTT (what latency_ms holds) and
    # the check's own p95 (falling back to the median for checks without one).
    # Hourly rows stand in for all of their checks, weighted by how many there were.
    median_pairs = [(lat, 1.0) for lat, _ in points]
    p95_pairs = [(p95, 1.0) for _, p95 in points]
    for h in hourly:
        if h["avg_median_ms"] is not None:
            median_pairs.append((h["avg_median_ms"], float(h["sample_count"])))
            p95_pairs.append(
                (h["max_p95_ms"] if h["max_p95_ms"] is not None else h["avg_median_ms"], float(h["sample_count"]))
            )

    def combined_mean(raw_value: float | None, hourly_column: str) -> float | None:
        pairs = [(h[hourly_column], float(h["sample_count"])) for h in hourly if h[hourly_column] is not None]
        if raw_value is not None and raw_n:
            pairs.append((raw_value, float(raw_n)))
        return _weighted_mean(pairs)

    # Extremes are the lowest/highest single RTT seen (a burst's own min/max), falling
    # back to the check's latency for checks recorded before Burst Probing.
    mins = [v for v in [agg.get("min_rtt"), *(h["min_ms"] for h in hourly)] if v is not None]
    maxs = [v for v in [agg.get("max_rtt"), *(h["max_ms"] for h in hourly)] if v is not None]
    raw_latencies = sorted(lat for lat, _ in points)
    if hourly:
        median = weighted_percentile(median_pairs, 50) if median_pairs else None
        p95 = weighted_percentile(p95_pairs, 95) if p95_pairs else None
    else:  # raw only: exact, interpolated percentiles over every sample
        median = percentile(raw_latencies, 50) if raw_latencies else None
        p95 = percentile(sorted(v for v, _ in p95_pairs), 95) if p95_pairs else None
    avg_latency = _weighted_mean(median_pairs)

    first, last = agg.get("first_ts"), agg.get("last_ts")
    if hourly:
        first = min(filter(None, [first, hourly[0]["hour_bucket"]]))
        last = max(filter(None, [last, hourly[-1]["hour_bucket"]]))
    duration_seconds = _seconds_between(first, last)
    uptime_pct = uptime_percentage(duration_seconds, real_downtime_seconds, sleep_seconds)
    effective_seconds = max(0.0, duration_seconds - sleep_seconds)

    loss = combined_mean(agg.get("avg_packet_loss"), "avg_loss_pct")
    jitter = combined_mean(agg.get("avg_jitter"), "avg_jitter_ms")
    iqr = combined_mean(agg.get("avg_iqr"), "avg_iqr_ms")

    return StatisticsResponse(
        range_start=start_iso,
        range_end=end_iso,
        target_id=target_id,
        sample_count=sample_count,
        avg_latency_ms=round(avg_latency, 2) if avg_latency is not None else None,
        min_latency_ms=min(mins) if mins else None,
        max_latency_ms=max(maxs) if maxs else None,
        median_latency_ms=round(median, 2) if median is not None else None,
        p95_latency_ms=round(p95, 2) if p95 is not None else None,
        packet_loss_pct=round(loss, 2) if loss is not None else None,
        avg_jitter_ms=round(jitter, 2) if jitter is not None else None,
        avg_iqr_ms=round(iqr, 2) if iqr is not None else None,
        uptime_pct=uptime_pct,
        outage_count=outage_agg.get("outage_count") or 0,
        longest_outage_seconds=outage_agg.get("longest"),
        monitoring_duration_seconds=duration_seconds,
        downtime_seconds=round(real_downtime_seconds, 2),
        effective_monitored_seconds=round(effective_seconds, 2),
    )
