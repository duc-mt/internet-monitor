from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


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


class NotificationPreferences(BaseModel):
    on_offline: bool = True
    on_online: bool = True
    on_latency_threshold: bool = True
    on_packet_loss_threshold: bool = True
    on_outage_duration: bool = True
    cooldown_seconds: int = Field(default=60, ge=0, le=3600)


class AppSettings(BaseModel):
    # Monitoring
    ping_timeout_seconds: float = Field(default=2.0, ge=0.2, le=30)
    pings_per_check: int = Field(
        default=3, ge=1, le=10,
        description="Number of echo/connect attempts per check ('retries' in the UI)."
    )
    default_target_interval_seconds: int = Field(default=5, ge=1, le=3600)

    # Alert thresholds (separate from the quality classifier - these drive
    # desktop notifications specifically).
    latency_warning_threshold_ms: float = 150
    packet_loss_warning_threshold_pct: float = 5
    outage_threshold_checks: int = Field(
        default=3, ge=1, le=60,
        description="Consecutive failed checks, across all non-gateway targets, before an outage is recorded."
    )
    outage_notify_min_duration_seconds: int = 30

    notifications: NotificationPreferences = Field(default_factory=NotificationPreferences)
    classification: ClassificationThresholds = Field(default_factory=ClassificationThresholds)

    # Data lifecycle
    data_retention_days: int = Field(default=30, ge=1, le=3650)

    # Presentation / misc
    start_on_boot: bool = False
    theme: Literal["light", "dark", "system"] = "system"
    language: str = "en"


class AppSettingsUpdate(BaseModel):
    """All fields optional so PUT /api/settings can be a partial patch."""
    ping_timeout_seconds: Optional[float] = Field(default=None, ge=0.2, le=30)
    pings_per_check: Optional[int] = Field(default=None, ge=1, le=10)
    default_target_interval_seconds: Optional[int] = Field(default=None, ge=1, le=3600)
    latency_warning_threshold_ms: Optional[float] = None
    packet_loss_warning_threshold_pct: Optional[float] = None
    outage_threshold_checks: Optional[int] = Field(default=None, ge=1, le=60)
    outage_notify_min_duration_seconds: Optional[int] = None
    notifications: Optional[NotificationPreferences] = None
    classification: Optional[ClassificationThresholds] = None
    data_retention_days: Optional[int] = Field(default=None, ge=1, le=3650)
    start_on_boot: Optional[bool] = None
    theme: Optional[Literal["light", "dark", "system"]] = None
    language: Optional[str] = None
