"""
Best-effort detection of the network you're currently on (Wi-Fi SSID, or a
"Wired (<interface>)" label when not on Wi-Fi) - the context needed to tell
"50ms because you're on cafe Wi-Fi" apart from "50ms even though you're on
your home LAN".

This only matters for laptops that actually move between networks, so it's
explicitly a *lightweight, best-effort* lookup, not a full network-profiling
system:

- Results are cached (`_CACHE_TTL`) since the network you're on changes far
  less often than every 5-second ping check - without caching, every single
  measurement would spawn 2-3 extra subprocesses on top of the ping/TCP
  check already happening, which is exactly the kind of unnecessary
  overhead the brief asks to avoid.
- Every lookup is a short-timeout subprocess call with all errors treated
  as "unknown" rather than raised - a missing tool (e.g. no `nmcli` on a
  minimal Linux install) or a weird `route`/`networksetup` output must
  never take down a measurement, only leave `network_name` as None for it.
"""
from __future__ import annotations

import asyncio
import logging
import re
import sys
import time
from typing import Optional

logger = logging.getLogger("internet_monitor.network_info")

_IS_MACOS = sys.platform == "darwin"
_CACHE_TTL = 30.0  # seconds
_SUBPROCESS_TIMEOUT = 3.0

_cached_name: Optional[str] = None
_cache_updated_at: float = 0.0


async def get_network_name(force: bool = False) -> Optional[str]:
    """Returns something like "HomeWiFi" or "Wired (en0)", or None if it
    couldn't be determined (unsupported OS, missing tools, no connection)."""
    global _cached_name, _cache_updated_at
    now = time.monotonic()
    if not force and (now - _cache_updated_at) < _CACHE_TTL:
        return _cached_name

    try:
        _cached_name = await (_macos_network_name() if _IS_MACOS else _linux_network_name())
    except Exception:  # pragma: no cover - defensive: never let this break a measurement
        logger.debug("Network name detection failed", exc_info=True)
        _cached_name = None
    _cache_updated_at = now
    return _cached_name


def reset_cache() -> None:
    """Used by tests."""
    global _cached_name, _cache_updated_at
    _cached_name = None
    _cache_updated_at = 0.0


async def _run(*args: str) -> str:
    try:
        proc = await asyncio.create_subprocess_exec(
            *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=_SUBPROCESS_TIMEOUT)
        return stdout.decode(errors="replace")
    except (FileNotFoundError, asyncio.TimeoutError, OSError):
        return ""


# --- macOS ------------------------------------------------------------

async def _macos_network_name() -> Optional[str]:
    wifi_device = await _macos_wifi_device()
    default_iface = await _macos_default_route_interface()

    if wifi_device and default_iface == wifi_device:
        ssid = await _macos_ssid(wifi_device)
        return ssid or "Wi-Fi (unknown network)"
    if default_iface:
        return f"Wired ({default_iface})"
    return None


async def _macos_wifi_device() -> Optional[str]:
    output = await _run("networksetup", "-listallhardwareports")
    for block in output.split("\n\n"):
        if "Wi-Fi" in block or "AirPort" in block:
            m = re.search(r"Device:\s*(\S+)", block)
            if m:
                return m.group(1)
    return None


async def _macos_default_route_interface() -> Optional[str]:
    output = await _run("route", "-n", "get", "default")
    m = re.search(r"interface:\s*(\S+)", output)
    return m.group(1) if m else None


async def _macos_ssid(device: str) -> Optional[str]:
    output = await _run("networksetup", "-getairportnetwork", device)
    m = re.search(r"Current Wi-Fi Network:\s*(.+)", output)
    return m.group(1).strip() if m else None


async def get_default_gateway_macos() -> Optional[str]:
    """
    macOS-only default-gateway lookup (the same `route -n get default`
    parsed above for the interface, here for the gateway field instead).
    Used once, to seed the default "Gateway" target the first time a
    database is created (see app/database/targets_repo.py) - unlike
    get_network_name() above, this isn't cached, since it only ever runs
    once per fresh database rather than on every measurement.
    """
    output = await _run("route", "-n", "get", "default")
    m = re.search(r"gateway:\s*(\S+)", output)
    return m.group(1) if m else None


# --- Linux --------------------------------------------------------------

async def _linux_network_name() -> Optional[str]:
    ssid = (await _run("iwgetid", "-r")).strip()
    if ssid:
        return ssid

    output = await _run("nmcli", "-t", "-f", "active,ssid", "dev", "wifi")
    for line in output.splitlines():
        if line.startswith("yes:"):
            name = line.split(":", 1)[1].strip()
            if name:
                return name

    iface = await _linux_default_route_interface()
    return f"Wired ({iface})" if iface else None


async def _linux_default_route_interface() -> Optional[str]:
    output = await _run("ip", "route", "show", "default")
    m = re.search(r"\bdev\s+(\S+)", output)
    return m.group(1) if m else None
