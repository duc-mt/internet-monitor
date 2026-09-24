"""
Application-wide configuration.

Two layers of configuration exist deliberately:

1. Environment/deploy-time config (this module) - where the SQLite file
   lives, which host/port uvicorn binds to, log level. These rarely change
   and are fine as environment variables with sensible defaults.

2. User-tunable settings (app.services.settings_service.AppSettings) - things
   like thresholds and notification preferences that live in the `settings`
   table so they can be changed from the dashboard without restarting the
   service or touching the filesystem.
"""

from __future__ import annotations

import os
from pathlib import Path


def _default_data_dir() -> Path:
    """
    Follow the XDG base directory spec so the app behaves whether it is
    run as a systemd service (running as its own unprivileged user, with
    XDG_DATA_HOME pointed at /var/lib/internet-monitor by the unit file)
    or run manually by a developer out of a checkout.
    """
    xdg = os.environ.get("XDG_DATA_HOME")
    if xdg:
        return Path(xdg) / "internet-monitor"
    return Path.home() / ".local" / "share" / "internet-monitor"


DATA_DIR = Path(os.environ.get("INTERNET_MONITOR_DATA_DIR", _default_data_dir()))
DATABASE_PATH = DATA_DIR / "internet-monitor.db"

# The API must never be reachable off the local machine by default.
API_HOST = os.environ.get("INTERNET_MONITOR_HOST", "127.0.0.1")
API_PORT = int(os.environ.get("INTERNET_MONITOR_PORT", "8765"))

# Origins the dashboard may be served from during development (vite dev
# server). The production build is served by FastAPI itself from the same
# origin, so no CORS entry is needed for it.
DEV_CORS_ORIGINS = [
    "http://127.0.0.1:5173",
    "http://localhost:5173",
]

LOG_LEVEL = os.environ.get("INTERNET_MONITOR_LOG_LEVEL", "INFO")

# Absolute floor on how often any target may be checked, regardless of what
# a user requests in Settings/Targets. Protects against fat-fingering a
# 0-second interval and flooding the network.
MIN_INTERVAL_SECONDS = 1

# Built frontend, if present, is mounted at "/" by app.main.
FRONTEND_DIST_DIR = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"


def ensure_data_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
