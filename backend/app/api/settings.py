"""
==============================================================================
Module Name:   settings.py
Description:   Implementation and logic for settings.
Author:        Mai Tan Duc <ducmai.network@gmail.com>
Created:       2026-10-10
Version:       1.0.0
License:       MIT
==============================================================================
Usage:         python3 settings.py [options]
Notes:         Requires Python 3.8+
==============================================================================
"""
from __future__ import annotations

import aiosqlite
from fastapi import APIRouter, Depends

from app.api.deps import get_db
from app.models.settings import AppSettings, AppSettingsUpdate, mask_webhook_url
from app.services import settings_service

router = APIRouter(prefix="/api/settings", tags=["settings"])


def _redacted(settings: AppSettings) -> AppSettings:
    """
    The webhook URL is a credential (Slack/Discord embed a bearer token in
    it), so it never leaves the API in full - only here, at the boundary.
    Everywhere else (settings_service, the scheduler, notification_service)
    keeps working with the real value from the database.
    """
    out = settings.model_copy(deep=True)
    out.notifications.webhook_url = mask_webhook_url(out.notifications.webhook_url)
    return out


@router.get("", response_model=AppSettings)
async def get_settings(db: aiosqlite.Connection = Depends(get_db)):
    return _redacted(await settings_service.get_settings(db))


@router.put("", response_model=AppSettings)
async def update_settings(payload: AppSettingsUpdate, db: aiosqlite.Connection = Depends(get_db)):
    return _redacted(await settings_service.update_settings(db, payload))
