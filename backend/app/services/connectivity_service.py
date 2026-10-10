from __future__ import annotations

"""
==============================================================================
Module Name:   connectivity_service.py
Description:   Tracks whether "the Internet" is up as a single boolean, distinct from the more conservative outage-record logic in outage_service. This layer answers "is anything reachable right now" and fires the immediate went-offline/came-back-online notifications; outage_service answers "has every external target failed for long enough that this counts as a recorded outage" and owns the outages table.
Author:        Mai Tan Duc <ducmai.network@gmail.com>
Created:       2026-10-10
Version:       1.0.0
License:       MIT
==============================================================================
Usage:         python3 connectivity_service.py [options]
Notes:         Requires Python 3.8+
==============================================================================
"""


import logging

import aiosqlite

from app.database import measurements_repo, targets_repo
from app.models.settings import AppSettings
from app.services import notification_service

logger = logging.getLogger("internet_monitor.connectivity")

_previous_online: bool | None = None


async def evaluate(conn: aiosqlite.Connection, settings: AppSettings) -> bool:
    """Returns the current online state, having fired a notification on transition."""
    global _previous_online
    targets = await targets_repo.list_targets(conn, enabled_only=True)
    gateway_ids = {t.id for t in targets if t.is_gateway}
    latest = await measurements_repo.latest_measurements_all(conn)

    # Exclude gateway targets from internet reachability check when external targets exist
    external_measurements = [m for m in latest if m.target_id not in gateway_ids]
    if external_measurements:
        online = any(m.success for m in external_measurements)
    elif latest:
        online = any(m.success for m in latest)
    else:
        online = True  # no data yet: assume fine

    if _previous_online is not None and online != _previous_online:
        if not online and settings.notifications.on_offline:
            await notification_service.send(
                "Internet connection lost",
                "All monitored external targets stopped responding.",
                urgency="critical",
                key="global_offline",
                webhook_url=settings.notifications.webhook_url,
            )
        elif online and settings.notifications.on_online:
            await notification_service.send(
                "Internet connection restored",
                "Connectivity to monitored targets has resumed.",
                urgency="normal",
                key="global_online",
                webhook_url=settings.notifications.webhook_url,
            )
    _previous_online = online
    return online


def reset_state() -> None:
    """Used by tests."""
    global _previous_online
    _previous_online = None
