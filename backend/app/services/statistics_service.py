from __future__ import annotations

import statistics as pystats
from datetime import datetime, timedelta, timezone
from typing import Literal

import aiosqlite

from app.database import measurements_repo, outages_repo
from app.models.status import StatisticsResponse

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


def percentile(sorted_values: list[float], pct: float) -> float:
    n = len(sorted_values)
    if n == 1:
        return sorted_values[0]
    index = (pct / 100) * (n - 1)
    lower = int(index)
    upper = min(lower + 1, n - 1)
    weight = index - lower
    return sorted_values[lower] * (1 - weight) + sorted_values[upper] * weight


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

    latencies = await measurements_repo.latencies_in_range(conn, target_id=target_id, start=start_iso, end=end_iso)
    agg = await measurements_repo.aggregate_in_range(conn, target_id=target_id, start=start_iso, end=end_iso)
    outage_agg = await outages_repo.outage_stats_in_range(conn, start=start_iso, end=end_iso)
    real_downtime_seconds, sleep_seconds = await outages_repo.downtime_and_sleep_seconds_in_range(
        conn, start=start_iso, end=end_iso
    )

    sorted_latencies = sorted(latencies)
    duration_seconds = 0.0
    if agg.get("first_ts") and agg.get("last_ts"):
        try:
            first = datetime.fromisoformat(agg["first_ts"])
            last = datetime.fromisoformat(agg["last_ts"])
            duration_seconds = max(0.0, (last - first).total_seconds())
        except ValueError:
            duration_seconds = 0.0

    # Uptime% is computed over the time we actually observed (data coverage
    # minus detected sleep gaps), not the raw wall-clock size of the
    # requested range - a fresh install asked about "last 30 days" should
    # not be penalized (or flattered) for the days before it existed, and a
    # laptop that slept for 8 of the last 24 hours shouldn't have those 8
    # hours silently counted as either "up" or "down" - excluded from both
    # sides of the ratio, same as it's excluded from the outage log.
    effective_seconds = max(0.0, duration_seconds - sleep_seconds)
    uptime_pct = (
        round(max(0.0, 100 * (1 - real_downtime_seconds / effective_seconds)), 2) if effective_seconds > 0 else None
    )

    return StatisticsResponse(
        range_start=start_iso,
        range_end=end_iso,
        target_id=target_id,
        sample_count=agg.get("sample_count") or 0,
        avg_latency_ms=round(sum(sorted_latencies) / len(sorted_latencies), 2) if sorted_latencies else None,
        min_latency_ms=sorted_latencies[0] if sorted_latencies else None,
        max_latency_ms=sorted_latencies[-1] if sorted_latencies else None,
        median_latency_ms=round(pystats.median(sorted_latencies), 2) if sorted_latencies else None,
        p95_latency_ms=round(percentile(sorted_latencies, 95), 2) if sorted_latencies else None,
        packet_loss_pct=round(agg["avg_packet_loss"], 2) if agg.get("avg_packet_loss") is not None else None,
        avg_jitter_ms=round(agg["avg_jitter"], 2) if agg.get("avg_jitter") is not None else None,
        uptime_pct=uptime_pct,
        outage_count=outage_agg.get("outage_count") or 0,
        longest_outage_seconds=outage_agg.get("longest"),
        monitoring_duration_seconds=duration_seconds,
    )
