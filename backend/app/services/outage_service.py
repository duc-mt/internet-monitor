from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

import aiosqlite

from app.database import outages_repo, targets_repo
from app.models.settings import AppSettings
from app.services import notification_service

logger = logging.getLogger("internet_monitor.outages")

# Outage ids we've already sent a "still down" notification for, so we only
# send it once per outage rather than on every check past the threshold.
_duration_notified: set[int] = set()


async def evaluate(conn: aiosqlite.Connection, settings: AppSettings) -> None:
    """
    An outage is recorded when every enabled, non-gateway target has failed
    for at least `outage_threshold_checks` checks in a row. The gateway is
    excluded deliberately: a dead gateway means the LAN is down, which is a
    real problem but a different one from "the Internet is down", and mixing
    the two would make the outage log noisy for people on flaky Wi-Fi whose
    router occasionally drops a single ARP probe.
    """
    threshold = settings.outage_threshold_checks
    non_gateway = [t for t in await targets_repo.list_targets(conn, enabled_only=True) if not t.is_gateway]

    active = await outages_repo.get_active_outage(conn)

    if not non_gateway:
        return

    recent = await measurements_recent(conn, [t.id for t in non_gateway], threshold)
    all_down = all(len(recent.get(t.id, [])) >= threshold and not any(recent[t.id][:threshold]) for t in non_gateway)

    if all_down and active is None:
        outage = await outages_repo.start_outage(
            conn,
            reason="all monitored external targets unreachable",
            affected_targets=[t.name for t in non_gateway],
            failed_checks=threshold,
        )
        logger.warning("Outage started (#%s): %s", outage.id, outage.reason)
        # Feature 1: Advanced Probing (Traceroute) on outage
        asyncio.create_task(_run_diagnostic_traceroute([t.host for t in non_gateway]))
    elif not all_down and active is not None:
        closed = await outages_repo.end_active_outage(conn)
        _duration_notified.discard(active.id)
        if closed and settings.notifications.on_online:
            minutes = (closed.duration_seconds or 0) / 60
            await notification_service.send(
                "Outage resolved",
                f"Connectivity restored after {minutes:.1f} minute(s).",
                key=f"outage_end:{closed.id}",
            )

    # Duration-exceeded alert for an outage still in progress.
    if active is not None and settings.notifications.on_outage_duration and active.id not in _duration_notified:
        started = datetime.fromisoformat(active.started_at)
        elapsed = (datetime.now(timezone.utc) - started).total_seconds()
        if elapsed >= settings.outage_notify_min_duration_seconds:
            await notification_service.send(
                "Internet outage ongoing",
                f"No connectivity for over {int(elapsed)} seconds.",
                urgency="critical",
                key=f"outage_duration:{active.id}",
            )
            _duration_notified.add(active.id)


async def measurements_recent(conn: aiosqlite.Connection, target_ids: list[int], count: int) -> dict[int, list[bool]]:
    from app.database import measurements_repo

    return await measurements_repo.recent_results_for_targets(conn, target_ids, count)


def reset_state() -> None:
    """Used by tests."""
    _duration_notified.clear()


async def _run_diagnostic_traceroute(hosts: list[str]) -> None:
    """
    Runs a traceroute to the first available host to diagnose where the network is dropping packets.
    Logs the result to the backend logger.
    """
    if not hosts:
        return

    host = hosts[0]  # Just trace the first failed host (e.g. 8.8.8.8)
    logger.info(f"Running automated diagnostic traceroute to {host} due to outage...")

    import sys

    is_windows = sys.platform == "win32"

    if is_windows:
        args = ["tracert", "-d", "-h", "15", "-w", "1000", host]
    else:
        args = ["traceroute", "-n", "-m", "15", "-w", "1", host]

    try:
        proc = await asyncio.create_subprocess_exec(
            *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=30.0)
        output = stdout.decode(errors="replace").strip()
        logger.warning(f"Diagnostic Traceroute Result for {host}:\n{output}")
    except FileNotFoundError:
        logger.warning("Traceroute tool not found on this system. Skipping diagnostic.")
    except asyncio.TimeoutError:
        logger.warning(f"Diagnostic traceroute to {host} timed out.")
    except Exception as e:
        logger.warning(f"Diagnostic traceroute to {host} failed: {e}")
