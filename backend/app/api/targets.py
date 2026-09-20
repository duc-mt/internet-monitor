from __future__ import annotations

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_db
from app.database import targets_repo
from app.models.target import TargetCreate, TargetOut, TargetUpdate
from app.monitoring.scheduler import manager

router = APIRouter(prefix="/api/targets", tags=["targets"])


@router.get("", response_model=list[TargetOut])
async def list_targets(db: aiosqlite.Connection = Depends(get_db)):
    return await targets_repo.list_targets(db)


@router.post("", response_model=TargetOut, status_code=201)
async def create_target(payload: TargetCreate, db: aiosqlite.Connection = Depends(get_db)):
    target = await targets_repo.create_target(db, payload)
    await manager.reload_target(db, target.id)
    return target


@router.get("/{target_id}", response_model=TargetOut)
async def get_target(target_id: int, db: aiosqlite.Connection = Depends(get_db)):
    target = await targets_repo.get_target(db, target_id)
    if target is None:
        raise HTTPException(status_code=404, detail="Target not found")
    return target


@router.put("/{target_id}", response_model=TargetOut)
async def update_target(target_id: int, payload: TargetUpdate, db: aiosqlite.Connection = Depends(get_db)):
    target = await targets_repo.update_target(db, target_id, payload)
    if target is None:
        raise HTTPException(status_code=404, detail="Target not found")
    await manager.reload_target(db, target_id)
    return target


@router.delete("/{target_id}", status_code=204)
async def delete_target(target_id: int, db: aiosqlite.Connection = Depends(get_db)):
    deleted = await targets_repo.delete_target(db, target_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Target not found")
    await manager.reload_target(db, target_id)
    return None
