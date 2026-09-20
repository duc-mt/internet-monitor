from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

import aiosqlite

from app.config import MIN_INTERVAL_SECONDS
from app.database import measurements_repo, targets_repo
from app.models.measurement import MeasurementCreate
from app.models.settings import AppSettings
from app.models.target import TargetOut
from app.monitoring.pinger import PingBatchResult, run_check
from app.services import connectivity_service, notification_service, outage_service
from app.services.settings_service import get_settings

logger = logging.getLogger("internet_monitor.scheduler")

_INITIAL_CLEANUP_DELAY = 60
_CLEANUP_INTERVAL = 3600


class MonitoringManager:
    """
    Owns one asyncio task per enabled target, plus a shared task for
    retention cleanup. Outage/connectivity evaluation (which touch shared
    state - the single active-outage row) are serialized behind a lock so
    two target loops finishing at the same moment can't both decide to open
    a duplicate outage record.
    """

    def __init__(self) -> None:
        self._tasks: dict[int, asyncio.Task] = {}
        self._cleanup_task: Optional[asyncio.Task] = None
        self._running = False
        self._started_at: Optional[datetime] = None
        self._start_stop_lock = asyncio.Lock()
        self._eval_lock = asyncio.Lock()

    @property
    def running(self) -> bool:
        return self._running

    @property
    def started_at(self) -> Optional[datetime]:
        return self._started_at

    async def start(self, conn: aiosqlite.Connection) -> None:
        async with self._start_stop_lock:
            if self._running:
                return
            self._running = True
            self._started_at = datetime.now(timezone.utc)
            targets = await targets_repo.list_targets(conn, enabled_only=True)
            for target in targets:
                self._spawn(conn, target)
            self._cleanup_task = asyncio.create_task(self._cleanup_loop(conn), name="retention-cleanup")
            logger.info("Monitoring started with %d target(s)", len(targets))

    async def stop(self) -> None:
        async with self._start_stop_lock:
            if not self._running:
                return
            self._running = False
            tasks = list(self._tasks.values())
            if self._cleanup_task:
                tasks.append(self._cleanup_task)
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            self._tasks.clear()
            self._cleanup_task = None
            logger.info("Monitoring stopped")

    async def reload_target(self, conn: aiosqlite.Connection, target_id: int) -> None:
        """Call after a target is created/updated/deleted so the running
        set of loops reflects the change without a full restart."""
        existing = self._tasks.pop(target_id, None)
        if existing:
            existing.cancel()
        if not self._running:
            return
        target = await targets_repo.get_target(conn, target_id)
        if target and target.enabled:
            self._spawn(conn, target)

    def _spawn(self, conn: aiosqlite.Connection, target: TargetOut) -> None:
        task = asyncio.create_task(self._monitor_loop(conn, target), name=f"monitor-{target.id}")
        self._tasks[target.id] = task

    async def _monitor_loop(self, conn: aiosqlite.Connection, target: TargetOut) -> None:
        current = target
        while True:
            try:
                settings = await get_settings(conn)
                result = await run_check(
                    host=current.host, protocol=current.protocol, port=current.port,
                    count=settings.pings_per_check, timeout=settings.ping_timeout_seconds,
                )
                await measurements_repo.insert_measurement(conn, MeasurementCreate(
                    target_id=current.id,
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    latency_ms=result.avg_latency_ms,
                    packet_loss=result.loss_pct,
                    jitter_ms=result.jitter_ms,
                    success=result.success,
                    error=result.error,
                ))
                await self._check_thresholds(current, result, settings)
                async with self._eval_lock:
                    await connectivity_service.evaluate(conn, settings)
                    await outage_service.evaluate(conn, settings)
            except asyncio.CancelledError:
                raise
            except Exception:  # pragma: no cover - defensive: one bad check must not kill the loop
                logger.exception("Unexpected error monitoring target %s (%s)", current.name, current.host)

            fresh = await targets_repo.get_target(conn, current.id)
            if fresh is None or not fresh.enabled:
                self._tasks.pop(current.id, None)
                return
            current = fresh
            await asyncio.sleep(max(MIN_INTERVAL_SECONDS, current.interval_seconds))

    async def _check_thresholds(
        self, target: TargetOut, result: PingBatchResult, settings: AppSettings
    ) -> None:
        cooldown = settings.notifications.cooldown_seconds
        if (
            result.avg_latency_ms is not None
            and result.avg_latency_ms > settings.latency_warning_threshold_ms
            and settings.notifications.on_latency_threshold
        ):
            await notification_service.send(
                f"High latency: {target.name}",
                f"{result.avg_latency_ms:.0f} ms (threshold {settings.latency_warning_threshold_ms:.0f} ms)",
                key=f"latency:{target.id}", cooldown_seconds=cooldown,
            )
        if result.loss_pct > settings.packet_loss_warning_threshold_pct and settings.notifications.on_packet_loss_threshold:
            await notification_service.send(
                f"Packet loss: {target.name}",
                f"{result.loss_pct:.0f}% loss (threshold {settings.packet_loss_warning_threshold_pct:.0f}%)",
                key=f"loss:{target.id}", cooldown_seconds=cooldown,
            )

    async def _cleanup_loop(self, conn: aiosqlite.Connection) -> None:
        try:
            await asyncio.sleep(_INITIAL_CLEANUP_DELAY)
            while True:
                settings = await get_settings(conn)
                deleted = await measurements_repo.delete_older_than(conn, settings.data_retention_days)
                if deleted:
                    logger.info("Retention cleanup removed %d measurement row(s)", deleted)
                await asyncio.sleep(_CLEANUP_INTERVAL)
        except asyncio.CancelledError:
            raise


manager = MonitoringManager()
