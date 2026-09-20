from __future__ import annotations

import aiosqlite

from app.database import settings_repo
from app.models.settings import AppSettings, AppSettingsUpdate

_cached: AppSettings | None = None


async def get_settings(conn: aiosqlite.Connection) -> AppSettings:
    global _cached
    if _cached is not None:
        return _cached
    raw = await settings_repo.load_raw_settings(conn)
    _cached = AppSettings(**raw) if raw else AppSettings()
    if raw is None:
        # Persist defaults on first run so the settings table always has a row.
        await settings_repo.save_raw_settings(conn, _cached.model_dump())
    return _cached


_NESTED_FIELDS = ("notifications", "classification")


async def update_settings(conn: aiosqlite.Connection, patch: AppSettingsUpdate) -> AppSettings:
    """
    Partial update (PUT is treated as a patch, matching the dashboard's
    "change one setting" UX). Nested objects (notifications, classification)
    are merged key-by-key rather than replaced wholesale, so patching
    `notifications.on_offline` doesn't silently reset
    `notifications.cooldown_seconds` back to its default.
    """
    global _cached
    current = await get_settings(conn)
    current_dict = current.model_dump()
    updates = patch.model_dump(exclude_unset=True)

    for field in _NESTED_FIELDS:
        if field in updates:
            merged_nested = {**current_dict[field], **updates[field]}
            updates[field] = merged_nested

    merged_dict = {**current_dict, **updates}
    merged = AppSettings(**merged_dict)
    await settings_repo.save_raw_settings(conn, merged.model_dump())
    _cached = merged
    return merged


def invalidate_cache() -> None:
    """Used by tests to force a reload from the database."""
    global _cached
    _cached = None
