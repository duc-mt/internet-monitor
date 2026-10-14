"""
==============================================================================
Module Name:   scheduler.py
Description:   Source module scheduler.py.
Author:        Mai Tan Duc <ducmai.network@gmail.com>
Created:       2026-10-10
Version:       1.0.0
License:       MIT
==============================================================================
Usage:         python3 scheduler.py [options]
Notes:         Requires Python 3.8+
==============================================================================
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

import aiosqlite

from app.config import MIN_INTERVAL_SECONDS
from app.database import measurements_repo, targets_repo
from app.models.measurement import MeasurementCreate
from app.models.settings import AppSettings
from app.models.target import TargetOut
from app.monitoring import network_info
from app.monitoring.burst_prober import run_burst
from app.monitoring.burst_stats import BurstMetric
from app.services import (
    connectivity_service,
    notification_service,
    outage_service,
    sleep_service,
)
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
        self._cleanup_task: asyncio.Task | None = None
        self._running = False
        self._started_at: datetime | None = None
        self._start_stop_lock = asyncio.Lock()
        self._eval_lock = asyncio.Lock()

    @property
    def running(self) -> bool:
        return self._running

    @property
    def started_at(self) -> datetime | None:
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
                metric = await run_burst(
                    host=current.host,
                    protocol=current.protocol,
                    port=current.port,
                    count=settings.burst_packet_count,
                    interval_ms=settings.burst_interval_ms,
                    timeout=settings.ping_timeout_seconds,
                )
                # Cached (see network_info._CACHE_TTL) - this does not spawn
                # a fresh subprocess on every single check.
                network_name = await network_info.get_network_name()
                await measurements_repo.insert_measurement(
                    conn,
                    MeasurementCreate(
                        target_id=current.id,
                        timestamp=datetime.now(timezone.utc).isoformat(),
                        # The long-standing columns mirror the burst's median RTT and
                        # RFC 3550 jitter, so every older reader keeps seeing sensible numbers.
                        latency_ms=metric.median_rtt,
                        packet_loss=metric.loss_percent,
                        jitter_ms=metric.jitter_rfc3550,
                        success=metric.success,
                        error=metric.error,
                        network_name=network_name,
                        median_ms=metric.median_rtt,
                        p25_ms=metric.p25_rtt,
                        p75_ms=metric.p75_rtt,
                        p95_ms=metric.p95_rtt,
                        min_ms=metric.min_rtt,
                        max_ms=metric.max_rtt,
                        iqr_ms=metric.iqr_rtt,
                        jitter_rfc3550=metric.jitter_rfc3550,
                        packet_count=metric.packet_count,
                    ),
                )
                await self._check_thresholds(current, metric, settings)
                async with self._eval_lock:
                    # Sleep-gap check first: it only ever *records* a
                    # closed system_sleep row from state it already had, it
                    # never reads the outcome of this check's own insert
                    # below, so ordering relative to connectivity/outage
                    # evaluation doesn't matter for correctness - this order
                    # just keeps the "did we just wake up" signal freshest.
                    await sleep_service.check_gap(conn, settings.sleep_gap_threshold_seconds)
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

    async def _check_thresholds(self, target: TargetOut, metric: BurstMetric, settings: AppSettings) -> None:
        cooldown = settings.notifications.cooldown_seconds
        if (
            metric.median_rtt is not None
            and metric.median_rtt > settings.latency_warning_threshold_ms
            and settings.notifications.on_latency_threshold
        ):
            await notification_service.send(
                f"High latency: {target.name}",
                f"{metric.median_rtt:.0f} ms (threshold {settings.latency_warning_threshold_ms:.0f} ms)",
                key=f"latency:{target.id}",
                cooldown_seconds=cooldown,
                webhook_url=settings.notifications.webhook_url,
            )
        if (
            metric.loss_percent > settings.packet_loss_warning_threshold_pct
            and settings.notifications.on_packet_loss_threshold
        ):
            await notification_service.send(
                f"Packet loss: {target.name}",
                f"{metric.loss_percent:.0f}% loss (threshold {settings.packet_loss_warning_threshold_pct:.0f}%)",
                key=f"loss:{target.id}",
                cooldown_seconds=cooldown,
                webhook_url=settings.notifications.webhook_url,
            )

    async def _cleanup_loop(self, conn: aiosqlite.Connection) -> None:
        """Hourly: fold raw bursts older than raw_retention_days into hourly rows,
        drop hourly rows older than data_retention_days, then trim the WAL."""
        try:
            await asyncio.sleep(_INITIAL_CLEANUP_DELAY)
            while True:
                try:
                    await self.run_maintenance(conn)
                except asyncio.CancelledError:
                    raise
                except Exception:  # pragma: no cover - defensive: a failed pass is retried next hour
                    logger.exception("Retention/rollup pass failed")
                await asyncio.sleep(_CLEANUP_INTERVAL)
        except asyncio.CancelledError:
            raise

    @staticmethod
    async def run_maintenance(conn: aiosqlite.Connection) -> None:
        settings = await get_settings(conn)
        rolled = await measurements_repo.rollup_older_than(conn, raw_retention_days=settings.raw_retention_days)
        if rolled.raw_rows_deleted:
            logger.info(
                "Rollup: %d raw check(s) older than %d day(s) folded into %d hourly bucket(s)",
                rolled.raw_rows_deleted,
                settings.raw_retention_days,
                rolled.buckets_written,
            )
        expired = await measurements_repo.delete_hourly_older_than(conn, settings.data_retention_days)
        if expired:
            logger.info("Retention cleanup removed %d hourly bucket(s)", expired)
        if await measurements_repo.vacuum_if_fragmented(conn):
            logger.info("Database compacted after retention cleanup")
        await measurements_repo.checkpoint_wal(conn)


manager = MonitoringManager()
