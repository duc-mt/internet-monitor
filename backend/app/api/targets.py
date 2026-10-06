from __future__ import annotations

import time

import aiosqlite
from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_db
from app.database import targets_repo
from app.models.target import TargetCreate, TargetOut, TargetUpdate
from app.models.traceroute import TracerouteHopOut, TracerouteOut
from app.monitoring import traceroute
from app.monitoring.scheduler import manager

router = APIRouter(prefix="/api/targets", tags=["targets"])

# Target ids with a traceroute currently running. A trace can take up to ~a
# minute, so a second click on the same target is rejected rather than queued
# (different targets can still be traced in parallel).
_traces_in_flight: set[int] = set()


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


@router.post("/{target_id}/traceroute", response_model=TracerouteOut)
async def run_target_traceroute(target_id: int, db: aiosqlite.Connection = Depends(get_db)):
    """
    On-demand troubleshooting tool: trace the route to a target to see which
    hop (home router, ISP, or the destination) is slow or dropping packets.
    Manual only, like the speed test - nothing calls this on a timer.
    """
    target = await targets_repo.get_target(db, target_id)
    if target is None:
        raise HTTPException(status_code=404, detail="Target not found")
    if target_id in _traces_in_flight:
        raise HTTPException(status_code=409, detail="Traceroute already in progress for this target")

    _traces_in_flight.add(target_id)
    started = time.monotonic()
    try:
        result = await traceroute.run_traceroute(target.host)
    except traceroute.TracerouteUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    finally:
        _traces_in_flight.discard(target_id)

    return TracerouteOut(
        target_id=target.id,
        target_name=target.name,
        host=target.host,
        hops=[
            TracerouteHopOut(
                hop=h.hop,
                address=h.address,
                rtts_ms=h.rtts_ms,
                avg_ms=h.avg_ms,
                loss_pct=h.loss_pct,
                scope=h.scope,
                extra_addresses=h.extra_addresses,
            )
            for h in result.hops
        ],
        raw=result.raw,
        timed_out=result.timed_out,
        elapsed_seconds=round(time.monotonic() - started, 2),
    )
