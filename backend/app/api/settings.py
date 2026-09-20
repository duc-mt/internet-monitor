from __future__ import annotations

import aiosqlite
from fastapi import APIRouter, Depends

from app.api.deps import get_db
from app.models.settings import AppSettings, AppSettingsUpdate
from app.services import settings_service

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("", response_model=AppSettings)
async def get_settings(db: aiosqlite.Connection = Depends(get_db)):
    return await settings_service.get_settings(db)


@router.put("", response_model=AppSettings)
async def update_settings(payload: AppSettingsUpdate, db: aiosqlite.Connection = Depends(get_db)):
    return await settings_service.update_settings(db, payload)
