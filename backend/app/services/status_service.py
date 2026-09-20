from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import aiosqlite

from app.database import measurements_repo, outages_repo, targets_repo
from app.models.status import StatusResponse, TargetStatus
from app.monitoring import network_info
from app.services import quality_service
from app.services.settings_service import get_settings


async def compute_status(
    conn: aiosqlite.Connection, *, monitoring_started_at: Optional[datetime], monitoring_running: bool
) -> StatusResponse:
    settings = await get_settings(conn)
    targets = await targets_repo.list_targets(conn, enabled_only=True)
    latest_by_target = {m.target_id: m for m in await measurements_repo.latest_measurements_all(conn)}

    target_statuses: list[TargetStatus] = []
    reachable_count = 0
    have_any_measurement = bool(latest_by_target)

    headline_latencies: list[float] = []
    headline_losses: list[float] = []

    for t in targets:
        m = latest_by_target.get(t.id)
        reachable = bool(m and m.success)
        if reachable:
            reachable_count += 1
        target_statuses.append(TargetStatus(
            target_id=t.id, name=t.name, host=t.host,
            reachable=reachable,
            latency_ms=m.latency_ms if m else None,
            packet_loss=m.packet_loss if m else None,
            last_checked=m.timestamp if m else None,
        ))
        if not t.is_gateway and m is not None:
            if m.latency_ms is not None:
                headline_latencies.append(m.latency_ms)
            headline_losses.append(m.packet_loss)

    # Assume online until we have evidence otherwise (avoids a false
    # "Offline" flash during the first few seconds after startup).
    online = True if not have_any_measurement else reachable_count > 0

    avg_latency = round(sum(headline_latencies) / len(headline_latencies), 2) if headline_latencies else None
    avg_loss = round(sum(headline_losses) / len(headline_losses), 2) if headline_losses else None
    jitter_values = [m.jitter_ms for m in latest_by_target.values() if m.jitter_ms is not None]
    avg_jitter = round(sum(jitter_values) / len(jitter_values), 2) if jitter_values else None

    quality = "offline" if (have_any_measurement and not online) else quality_service.classify(
        avg_latency, avg_loss, settings.classification
    )

    uptime = 0.0
    if monitoring_running and monitoring_started_at is not None:
        uptime = (datetime.now(timezone.utc) - monitoring_started_at).total_seconds()

    active_outage = await outages_repo.get_active_outage(conn)
    network_name = await network_info.get_network_name()

    return StatusResponse(
        online=online,
        quality=quality,
        latency_ms=avg_latency,
        packet_loss=avg_loss,
        jitter_ms=avg_jitter,
        network_name=network_name,
        monitoring_uptime_seconds=uptime,
        targets_reachable=reachable_count,
        targets_total=len(targets),
        targets=target_statuses,
        active_outage=active_outage is not None,
        monitoring_running=monitoring_running,
    )
