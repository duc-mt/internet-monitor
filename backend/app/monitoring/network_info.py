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
import urllib.request
from typing import Optional

logger = logging.getLogger("internet_monitor.network_info")

_IS_MACOS = sys.platform == "darwin"
_IS_WINDOWS = sys.platform == "win32"
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
        if _IS_MACOS:
            _cached_name = await _macos_network_name()
        elif _IS_WINDOWS:
            _cached_name = await _windows_network_name()
        else:
            _cached_name = await _linux_network_name()
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


async def _run(*args: str, timeout: float = _SUBPROCESS_TIMEOUT) -> str:
    try:
        proc = await asyncio.create_subprocess_exec(
            *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
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
    if m:
        return m.group(1).strip()
    # macOS 15 (Sequoia) onward, `networksetup -getairportnetwork` no
    # longer returns a real SSID at all - a deliberate Location Services
    # privacy restriction (confirmed via macadmin community reports), not
    # something a regex against its output can work around. system_profiler
    # isn't subject to the same restriction, so fall back to it.
    return await _macos_ssid_via_system_profiler()


# Matches a bare "<name>:" line immediately under "Current Network
# Information:" - i.e. the SSID acting as a nested section header, with
# nothing else on that line. This is what tells it apart from a plain
# "Key: Value" line (which has non-whitespace after the colon and so
# cannot match here) - notably the awdl0 (AirDrop) pseudo-interface, whose
# own "Current Network Information:" block has no name header at all and
# goes straight to "Network Type: Infrastructure".
_SYSTEM_PROFILER_SSID_RE = re.compile(r"Current Network Information:\r?\n\s*([^\r\n:]+):[ \t]*\r?\n")


async def _macos_ssid_via_system_profiler() -> Optional[str]:
    """
    Noticeably slower than the other lookups here (system_profiler
    enumerates hardware, sometimes taking a few seconds) - acceptable
    since the overall result is cached for _CACHE_TTL regardless of which
    method produced it, and this is only reached at all once the fast
    networksetup path has already failed.
    """
    output = await _run("system_profiler", "SPAirPortDataType", "-detailLevel", "basic", timeout=8.0)
    m = _SYSTEM_PROFILER_SSID_RE.search(output)
    return m.group(1).strip() if m else None


# Anchored to line-start: "    SSID   : Name" matches, but "    BSSID   : ..."
# never can, since the very next characters after leading whitespace must
# literally be "SSID" - "BSSID" fails that immediately (starts with "B").
_WINDOWS_SSID_RE = re.compile(r"^\s*SSID\s*:\s*(.+?)\s*$", re.MULTILINE)


async def _windows_network_name() -> Optional[str]:
    output = await _run("netsh", "wlan", "show", "interfaces")
    m = _WINDOWS_SSID_RE.search(output)
    if m:
        return m.group(1).strip()
    # No Wi-Fi SSID - either no Wi-Fi adapter, or connected via Ethernet
    # instead. Windows has no single clean command correlating "the
    # interface the default route uses" with "is that Ethernet" the way
    # macOS's `route -n get default` + `networksetup` combination does, so
    # this is deliberately less precise than the macOS/Linux versions: a
    # generic "Wired" label whenever there's a working default route at
    # all, rather than the specific adapter name.
    gateway = await get_default_gateway_windows()
    return "Wired" if gateway else None


_WINDOWS_DEFAULT_ROUTE_RE = re.compile(r"^\s*0\.0\.0\.0\s+0\.0\.0\.0\s+(\d+\.\d+\.\d+\.\d+)", re.MULTILINE)


async def get_default_gateway_windows() -> Optional[str]:
    """
    Windows-only default-gateway lookup via `route print -4`'s IPv4 route
    table, which has exactly one row for the 0.0.0.0/0.0.0.0 (default)
    destination - route.exe is a standalone executable (not a cmd.exe
    built-in), so it can be spawned directly like any other subprocess
    here. Used once, same as get_default_gateway_macos() - see
    app/database/targets_repo.py.
    """
    output = await _run("route", "print", "-4")
    m = _WINDOWS_DEFAULT_ROUTE_RE.search(output)
    return m.group(1) if m else None


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


async def get_wan_ip() -> Optional[str]:
    """
    Fetch the public WAN IP address using icanhazip.com.
    Done in a thread to avoid blocking the async event loop.
    """
    def _fetch():
        req = urllib.request.Request("http://ipv4.icanhazip.com", headers={'User-Agent': 'curl/7.68.0'})
        with urllib.request.urlopen(req, timeout=5.0) as response:
            return response.read().decode('utf-8').strip()
    try:
        return await asyncio.to_thread(_fetch)
    except Exception as e:
        logger.debug(f"Failed to detect WAN IP: {e}")
        return None
