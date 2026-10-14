"""
==============================================================================
Module Name:   settings.py
Description:   Source module settings.py.
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

from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, Field, field_validator


class ClassificationThresholds(BaseModel):
    """
    Boundaries for the quality classifier. Never hard-coded into the UI -
    the UI reads these back from /api/settings and renders whatever it is
    given, so changing a number here changes the dashboard immediately.
    """

    excellent_latency_ms: float = 30
    excellent_packet_loss_pct: float = 1
    good_latency_ms: float = 60
    good_packet_loss_pct: float = 2
    fair_latency_ms: float = 100
    fair_packet_loss_pct: float = 5


class StabilityThresholds(BaseModel):
    """
    Boundaries for the STABILITY SCORE, which judges a burst by its IQR (the
    core latency variation) and its packet loss rather than by the latency
    itself. Loss thresholds are in percent of the probes of one burst: with the
    default 15-probe burst a single lost probe is 6.67 %, so "good" tolerates
    exactly one.
    """

    excellent_iqr_ms: float = Field(default=5, ge=0)  # excellent also requires loss == 0
    good_iqr_ms: float = Field(default=15, ge=0)
    good_loss_pct: float = Field(default=7, ge=0, le=100)
    fair_iqr_ms: float = Field(default=30, ge=0)
    fair_loss_pct: float = Field(default=15, ge=0, le=100)


class NotificationPreferences(BaseModel):
    on_offline: bool = True
    on_online: bool = True
    on_latency_threshold: bool = True
    on_packet_loss_threshold: bool = True
    on_outage_duration: bool = True
    cooldown_seconds: int = Field(default=60, ge=0, le=3600)
    # Optional HTTP webhook (Slack, Discord, or any endpoint that accepts a JSON
    # POST) so alerts also reach headless servers with no desktop to notify.
    # Treat the value as a secret: Slack and Discord webhook URLs embed their token.
    webhook_url: str | None = Field(default=None, max_length=2048)

    @field_validator("webhook_url")
    @classmethod
    def _validate_webhook_url(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        if not v:  # the settings form sends "" when the field is cleared
            return None
        parts = urlsplit(v)
        if parts.scheme not in ("http", "https") or not parts.hostname:
            raise ValueError("webhook_url must be an http:// or https:// URL")
        return v


# A fixed-width placeholder, not the URL's real length, so the mask itself
# gives no hint about how long the embedded Slack/Discord token is.
_WEBHOOK_MASK_SUFFIX = "\u2022" * 8  # "••••••••"


def mask_webhook_url(url: str | None) -> str | None:
    """
    What a webhook URL looks like once it leaves the server: scheme and host
    are kept (useful for recognizing "yes, this points at Slack"), the path
    and query - where Slack/Discord embed the actual bearer token - are
    replaced. Deterministic for a given URL, so the API layer can tell a
    genuine new value apart from the client simply echoing back what GET
    returned.
    """
    if not url:
        return None
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.hostname}/{_WEBHOOK_MASK_SUFFIX}"


class AppSettings(BaseModel):
    # Monitoring
    ping_timeout_seconds: float = Field(default=2.0, ge=0.2, le=30)
    burst_packet_count: int = Field(
        default=15, ge=10, le=20, description="ICMP/TCP probes sent back-to-back in one Burst Probing cycle."
    )
    burst_interval_ms: int = Field(
        default=20, ge=15, le=20, description="Pause between two probes of a burst, in milliseconds."
    )
    default_target_interval_seconds: int = Field(
        default=60, ge=1, le=3600, description="Seconds between two bursts against a target."
    )

    # Alert thresholds (separate from the quality classifier - these drive
    # desktop notifications specifically).
    latency_warning_threshold_ms: float = 150
    packet_loss_warning_threshold_pct: float = 5
    outage_threshold_checks: int = Field(
        default=3,
        ge=1,
        le=60,
        description="Consecutive failed checks, across all non-gateway targets, before an outage is recorded.",
    )
    outage_notify_min_duration_seconds: int = 30
    sleep_gap_threshold_seconds: int = Field(
        default=60,
        ge=10,
        le=3600,
        description=(
            "If the gap between two consecutive monitoring ticks exceeds this, "
            "the laptop almost certainly slept in between - that gap is recorded "
            "as a 'system_sleep' event and excluded from downtime/uptime %, "
            "rather than being misread as a real internet outage."
        ),
    )

    sla_target_pct: float = Field(
        default=99.9,
        gt=0,
        le=100,
        description=(
            "Uptime target from the ISP contract (e.g. 99.9). The dashboard turns it into an error budget: "
            "the downtime allowed over the monitored period before the SLA is breached."
        ),
    )

    notifications: NotificationPreferences = Field(default_factory=NotificationPreferences)
    classification: ClassificationThresholds = Field(default_factory=ClassificationThresholds)
    stability: StabilityThresholds = Field(default_factory=StabilityThresholds)

    # Data lifecycle: one row per burst is kept for `raw_retention_days`, then
    # folded into one row per target per hour, kept for `data_retention_days`.
    raw_retention_days: int = Field(default=7, ge=1, le=90)
    data_retention_days: int = Field(default=90, ge=1, le=3650)

    # Presentation / misc
    start_on_boot: bool = False
    theme: Literal["light", "dark", "system"] = "system"
    language: str = "en"


class AppSettingsUpdate(BaseModel):
    """All fields optional so PUT /api/settings can be a partial patch."""

    ping_timeout_seconds: float | None = Field(default=None, ge=0.2, le=30)
    burst_packet_count: int | None = Field(default=None, ge=10, le=20)
    burst_interval_ms: int | None = Field(default=None, ge=15, le=20)
    default_target_interval_seconds: int | None = Field(default=None, ge=1, le=3600)
    latency_warning_threshold_ms: float | None = None
    packet_loss_warning_threshold_pct: float | None = None
    outage_threshold_checks: int | None = Field(default=None, ge=1, le=60)
    outage_notify_min_duration_seconds: int | None = None
    sleep_gap_threshold_seconds: int | None = Field(default=None, ge=10, le=3600)
    sla_target_pct: float | None = Field(default=None, gt=0, le=100)
    notifications: NotificationPreferences | None = None
    classification: ClassificationThresholds | None = None
    stability: StabilityThresholds | None = None
    raw_retention_days: int | None = Field(default=None, ge=1, le=90)
    data_retention_days: int | None = Field(default=None, ge=1, le=3650)
    start_on_boot: bool | None = None
    theme: Literal["light", "dark", "system"] | None = None
    language: str | None = None
