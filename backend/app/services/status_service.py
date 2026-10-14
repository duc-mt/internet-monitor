"""
==============================================================================
Module Name:   status_service.py
Description:   Source module status_service.py.
Author:        Mai Tan Duc <ducmai.network@gmail.com>
Created:       2026-10-10
Version:       1.0.0
License:       MIT
==============================================================================
Usage:         python3 status_service.py [options]
Notes:         Requires Python 3.8+
==============================================================================
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import aiosqlite

from app.database import measurements_repo, outages_repo, targets_repo
from app.models.status import StatusResponse, TargetStatus
from app.monitoring import network_info
from app.services import quality_service, statistics_service
from app.services.settings_service import get_settings


async def compute_status(
    conn: aiosqlite.Connection, *, monitoring_started_at: datetime | None, monitoring_running: bool
) -> StatusResponse:
    settings = await get_settings(conn)
    targets = await targets_repo.list_targets(conn, enabled_only=True)
    latest_by_target = {m.target_id: m for m in await measurements_repo.latest_measurements_all(conn)}

    target_statuses: list[TargetStatus] = []
    reachable_count = 0
    external_reachable_count = 0
    external_target_count = 0
    have_any_measurement = bool(latest_by_target)

    headline_latencies: list[float] = []
    headline_losses: list[float] = []
    headline_burst: dict[str, list[float]] = {"median_ms": [], "iqr_ms": [], "p95_ms": [], "jitter_rfc3550": []}

    for t in targets:
        m = latest_by_target.get(t.id)
        reachable = bool(m and m.success)
        if reachable:
            reachable_count += 1
        if not t.is_gateway:
            external_target_count += 1
            if reachable:
                external_reachable_count += 1
        target_statuses.append(
            TargetStatus(
                target_id=t.id,
                name=t.name,
                host=t.host,
                reachable=reachable,
                latency_ms=m.latency_ms if m else None,
                packet_loss=m.packet_loss if m else None,
                last_checked=m.timestamp if m else None,
                median_ms=m.median_ms if m else None,
                iqr_ms=m.iqr_ms if m else None,
                p95_ms=m.p95_ms if m else None,
                jitter_rfc3550_ms=m.jitter_rfc3550 if m else None,
            )
        )
        if not t.is_gateway and m is not None:
            if m.latency_ms is not None:
                headline_latencies.append(m.latency_ms)
            headline_losses.append(m.packet_loss)
            for field, values in headline_burst.items():
                value = getattr(m, field)
                if value is not None:
                    values.append(value)

    # Assume online until we have evidence otherwise (avoids a false
    # "Offline" flash during the first few seconds after startup).
    if not have_any_measurement:
        online = True
    elif external_target_count > 0:
        online = external_reachable_count > 0
    else:
        online = reachable_count > 0

    avg_latency = round(sum(headline_latencies) / len(headline_latencies), 2) if headline_latencies else None
    avg_loss = round(sum(headline_losses) / len(headline_losses), 2) if headline_losses else None
    jitter_values = [m.jitter_ms for m in latest_by_target.values() if m.jitter_ms is not None]
    avg_jitter = round(sum(jitter_values) / len(jitter_values), 2) if jitter_values else None

    quality = (
        "offline"
        if (have_any_measurement and not online)
        else quality_service.classify(avg_latency, avg_loss, settings.classification)
    )

    def mean(values: list[float]) -> float | None:
        return round(sum(values) / len(values), 2) if values else None

    avg_median = mean(headline_burst["median_ms"])
    avg_iqr = mean(headline_burst["iqr_ms"])
    avg_p95 = mean(headline_burst["p95_ms"])
    avg_rfc_jitter = mean(headline_burst["jitter_rfc3550"])
    # Stability needs a burst's IQR; offline trumps it, as it does for quality.
    stability = (
        "unknown"
        if (have_any_measurement and not online)
        else quality_service.classify_stability(avg_iqr, avg_loss, settings.stability)
    )

    uptime = 0.0
    if monitoring_running and monitoring_started_at is not None:
        uptime = (datetime.now(timezone.utc) - monitoring_started_at).total_seconds()

    active_outage = await outages_repo.get_active_outage(conn)
    network_name = await network_info.get_network_name()
    # Same downtime/sleep-exclusion maths as the History page's range stats,
    # but through the lightweight path: this runs on every /api/status poll
    # (every few seconds), so it must not load and sort a day of samples.
    uptime_pct_24h = await statistics_service.compute_uptime_pct(conn, window=timedelta(hours=24))

    return StatusResponse(
        online=online,
        quality=quality,
        latency_ms=avg_latency,
        packet_loss=avg_loss,
        jitter_ms=avg_jitter,
        median_ms=avg_median,
        iqr_ms=avg_iqr,
        p95_ms=avg_p95,
        jitter_rfc3550_ms=avg_rfc_jitter,
        stability=stability,
        network_name=network_name,
        monitoring_uptime_seconds=uptime,
        uptime_pct_24h=uptime_pct_24h,
        targets_reachable=reachable_count,
        targets_total=len(targets),
        targets=target_statuses,
        active_outage=active_outage is not None,
        monitoring_running=monitoring_running,
    )
