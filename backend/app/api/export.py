from __future__ import annotations

import csv
import io

import aiosqlite
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.api.deps import get_db
from app.database import measurements_repo, outages_repo
from app.services import statistics_service

router = APIRouter(prefix="/api/export", tags=["export"])


@router.get("/measurements.csv")
async def export_measurements_csv(
    target_id: int | None = None,
    start: str | None = None,
    end: str | None = None,
    db: aiosqlite.Connection = Depends(get_db),
):
    rows = await measurements_repo.list_measurements(db, target_id=target_id, start=start, end=end, limit=100000)
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "timestamp",
            "target_id",
            "target_name",
            "latency_ms",
            "packet_loss",
            "jitter_ms",
            "success",
            "error",
            "network_name",
        ]
    )
    for r in rows:
        writer.writerow(
            [
                r.timestamp,
                r.target_id,
                r.target_name,
                r.latency_ms,
                r.packet_loss,
                r.jitter_ms,
                r.success,
                r.error or "",
                r.network_name or "",
            ]
        )
    buffer.seek(0)
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=internet-monitor-measurements.csv"},
    )


@router.get("/report.json")
async def export_report_json(
    range: statistics_service.RangeName = "24h",
    start: str | None = None,
    end: str | None = None,
    target_id: int | None = None,
    db: aiosqlite.Connection = Depends(get_db),
):
    stats = await statistics_service.compute_statistics(
        db,
        range_name=range,
        start=start,
        end=end,
        target_id=target_id,  # type: ignore[arg-type]
    )
    outages = await outages_repo.list_outages(db, start=stats.range_start, end=stats.range_end)
    report = {
        "statistics": stats.model_dump(),
        "outages": [o.model_dump() for o in outages],
    }
    buffer = io.StringIO()
    import json

    json.dump(report, buffer, indent=2)
    buffer.seek(0)
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="application/json",
        headers={"Content-Disposition": "attachment; filename=internet-monitor-report.json"},
    )
