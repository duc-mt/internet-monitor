"""
==============================================================================
Module Name:   export.py
Description:   Source module export.py.
Author:        Mai Tan Duc <ducmai.network@gmail.com>
Created:       2026-10-10
Version:       1.0.0
License:       MIT
==============================================================================
Usage:         python3 export.py [options]
Notes:         Requires Python 3.8+
==============================================================================
"""

from __future__ import annotations

import csv
import io
import json
from collections.abc import AsyncIterator

import aiosqlite
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.api.deps import get_db
from app.database import measurements_repo, outages_repo
from app.services import statistics_service

router = APIRouter(prefix="/api/export", tags=["export"])

# Same cap as before streaming existed; the point of streaming is that memory no longer scales with it.
EXPORT_MAX_ROWS = 100_000
_BATCH_ROWS = 1000

CSV_COLUMNS = [
    "timestamp",
    "target_id",
    "target_name",
    "latency_ms",
    "packet_loss",
    "jitter_ms",
    "success",
    "error",
    "network_name",
    # Burst Probing summary (appended, so existing column positions are unchanged)
    "median_ms",
    "p25_ms",
    "p75_ms",
    "p95_ms",
    "min_ms",
    "max_ms",
    "iqr_ms",
    "jitter_rfc3550",
    "packet_count",
]


def _csv_line(values: list) -> str:
    """One CSV record as text. A fresh buffer per line keeps this stateless: nothing accumulates between yields."""
    buffer = io.StringIO()
    csv.writer(buffer).writerow(["" if v is None else v for v in values])
    return buffer.getvalue()


async def _stream_measurements_csv(
    db: aiosqlite.Connection, target_id: int | None, start: str | None, end: str | None
) -> AsyncIterator[str]:
    yield _csv_line(CSV_COLUMNS)
    async for r in measurements_repo.iter_measurements(
        db, target_id=target_id, start=start, end=end, batch_size=_BATCH_ROWS, max_rows=EXPORT_MAX_ROWS
    ):
        yield _csv_line(
            [
                r.timestamp,
                r.target_id,
                r.target_name,
                r.latency_ms,
                r.packet_loss,
                r.jitter_ms,
                r.success,
                r.error,
                r.network_name,
                r.median_ms,
                r.p25_ms,
                r.p75_ms,
                r.p95_ms,
                r.min_ms,
                r.max_ms,
                r.iqr_ms,
                r.jitter_rfc3550,
                r.packet_count,
            ]
        )


@router.get("/measurements.csv")
async def export_measurements_csv(
    target_id: int | None = None,
    start: str | None = None,
    end: str | None = None,
    db: aiosqlite.Connection = Depends(get_db),
):
    # A real stream: rows are fetched a batch at a time and written to the socket
    # as they come, instead of being collected into one in-memory buffer first.
    return StreamingResponse(
        _stream_measurements_csv(db, target_id, start, end),
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
    # Small (one statistics block + the outage list), so it is built in one piece.
    return StreamingResponse(
        iter([json.dumps(report, indent=2)]),
        media_type="application/json",
        headers={"Content-Disposition": "attachment; filename=internet-monitor-report.json"},
    )
