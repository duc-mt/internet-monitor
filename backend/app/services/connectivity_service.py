"""
Tracks whether "the Internet" is up as a single boolean, distinct from the
more conservative outage-record logic in outage_service. This layer answers
"is anything reachable right now" and fires the immediate
went-offline/came-back-online notifications; outage_service answers "has
every external target failed for long enough that this counts as a
recorded outage" and owns the outages table.
"""
from __future__ import annotations

import logging
from typing import Optional

import aiosqlite

from app.database import measurements_repo
from app.models.settings import AppSettings
from app.services import notification_service

logger = logging.getLogger("internet_monitor.connectivity")

_previous_online: Optional[bool] = None


async def evaluate(conn: aiosqlite.Connection, settings: AppSettings) -> bool:
    """Returns the current online state, having fired a notification on transition."""
    global _previous_online
    latest = await measurements_repo.latest_measurements_all(conn)
    online = any(m.success for m in latest) if latest else True  # no data yet: assume fine

    if _previous_online is not None and online != _previous_online:
        if not online and settings.notifications.on_offline:
            await notification_service.send(
                "Internet connection lost",
                "All monitored targets stopped responding.",
                urgency="critical",
                key="global_offline",
            )
        elif online and settings.notifications.on_online:
            await notification_service.send(
                "Internet connection restored",
                "Connectivity to monitored targets has resumed.",
                urgency="normal",
                key="global_online",
            )
    _previous_online = online
    return online


def reset_state() -> None:
    """Used by tests."""
    global _previous_online
    _previous_online = None
