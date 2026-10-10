"""
==============================================================================
Module Name:   traceroute.py
Description:   Implementation and logic for traceroute.
Author:        Mai Tan Duc <ducmai.network@gmail.com>
Created:       2026-10-10
Version:       1.0.0
License:       MIT
==============================================================================
Usage:         python3 traceroute.py [options]
Notes:         Requires Python 3.8+
==============================================================================
"""
"""
On-demand and automatic traceroute, shared by the outage diagnostics and the
``POST /api/targets/{id}/traceroute`` troubleshooting endpoint.

Design notes:

- Stdlib only (``asyncio``, ``ipaddress``, ``re``) so it stays trivially
  testable and has no import-time cost.
- The platform tool is picked once per call: ``tracert`` on Windows,
  ``traceroute`` elsewhere. Both are run with DNS resolution disabled
  (``-d`` / ``-n``) - reverse lookups on a path that is already dropping
  packets are slow and would blow the time budget.
- The parser is structural, not locale-based: a hop line is "a line that
  starts with an integer", RTTs are ``<number> ms`` tokens, a lone ``*`` is
  a lost probe, and an address is any token that ``ipaddress`` accepts. That
  keeps it working on localized Windows output ("Request timed out." in
  another language) and on the slightly different layouts of GNU and BSD
  traceroute.
- Output is collected incrementally, so when the overall time budget runs
  out the hops that *were* resolved are still returned (``timed_out=True``)
  instead of throwing everything away.
"""

from __future__ import annotations

import asyncio
import ipaddress
import logging
import re
import sys
from contextlib import suppress
from dataclasses import dataclass, field
from typing import Literal

logger = logging.getLogger("internet_monitor.traceroute")

DEFAULT_MAX_HOPS = 15
DEFAULT_PROBE_TIMEOUT_SECONDS = 1.0
PROBES_PER_HOP = 3  # fixed by tracert; matches the traceroute default

Scope = Literal["private", "cgnat", "public", "unknown"]

_CGNAT_NETWORK = ipaddress.ip_network("100.64.0.0/10")  # RFC 6598 carrier-grade NAT
_HOP_LINE_RE = re.compile(r"^\s*(\d{1,3})\s+(\S.*)$")
# One probe result: either a lone "*" (lost) or "<number> ms", optionally with
# tracert's "<" prefix for sub-millisecond replies ("<1 ms").
_PROBE_RE = re.compile(
    r"(?P<star>(?<!\S)\*(?!\S))|(?P<lt><)?\s*(?P<ms>\d+(?:[.,]\d+)?)\s*ms\b",
    re.IGNORECASE,
)


class TracerouteError(Exception):
    """Base class for failures the API layer maps to an HTTP error."""


class TracerouteUnavailable(TracerouteError):
    """The platform traceroute binary is not installed."""


@dataclass
class Hop:
    hop: int
    address: str | None
    rtts_ms: list[float | None]
    scope: Scope = "unknown"
    extra_addresses: list[str] = field(default_factory=list)

    @property
    def avg_ms(self) -> float | None:
        answered = [r for r in self.rtts_ms if r is not None]
        return round(sum(answered) / len(answered), 2) if answered else None

    @property
    def loss_pct(self) -> float:
        if not self.rtts_ms:
            return 100.0
        lost = sum(1 for r in self.rtts_ms if r is None)
        return round(100 * lost / len(self.rtts_ms), 1)


@dataclass
class TracerouteResult:
    host: str
    hops: list[Hop]
    raw: str
    timed_out: bool = False


def classify_address(address: str | None) -> Scope:
    """Where a hop sits on the path: your LAN, the ISP's CGNAT, or the public
    Internet. Hop 1 being ``private`` is the usual home router."""
    if address is None:
        return "unknown"
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return "unknown"
    if isinstance(ip, ipaddress.IPv4Address) and ip in _CGNAT_NETWORK:
        return "cgnat"
    if ip.is_private or ip.is_loopback or ip.is_link_local:
        return "private"
    return "public"


def _check_host(host: str) -> str:
    """Last-line defence before the host reaches a subprocess argv.

    Hosts are already validated when a target is stored (see
    ``app.models.target.validate_host``); this only guards against a value
    that could be read as an option flag or smuggle whitespace.
    """
    host = host.strip()
    if not host or host.startswith("-") or any(c.isspace() for c in host):
        raise ValueError(f"refusing to trace invalid host {host!r}")
    return host


def build_command(
    host: str,
    *,
    max_hops: int = DEFAULT_MAX_HOPS,
    probe_timeout_seconds: float = DEFAULT_PROBE_TIMEOUT_SECONDS,
    windows: bool | None = None,
) -> list[str]:
    host = _check_host(host)
    is_windows = (sys.platform == "win32") if windows is None else windows
    if is_windows:
        return ["tracert", "-d", "-h", str(max_hops), "-w", str(int(probe_timeout_seconds * 1000)), host]
    # "--" ends option parsing on GNU and BSD traceroute; tracert has no
    # equivalent, which is why _check_host rejects a leading "-" above.
    return [
        "traceroute",
        "-n",
        "-m",
        str(max_hops),
        "-w",
        str(max(1, int(round(probe_timeout_seconds)))),
        "--",
        host,
    ]


def parse_output(text: str) -> list[Hop]:
    hops: list[Hop] = []
    for line in text.splitlines():
        match = _HOP_LINE_RE.match(line)
        if not match:
            continue
        rest = match.group(2)
        addresses = _addresses_in(rest)
        hops.append(
            Hop(
                hop=int(match.group(1)),
                address=addresses[0] if addresses else None,
                rtts_ms=_probes_in(rest),
                scope=classify_address(addresses[0] if addresses else None),
                extra_addresses=addresses[1:],
            )
        )
    return hops


def _addresses_in(rest: str) -> list[str]:
    """Distinct IPs on a hop line, in order. A hop can list several when
    successive probes took different paths (ECMP / load balancing)."""
    found: list[str] = []
    for token in rest.split():
        try:
            ip = str(ipaddress.ip_address(token.strip("[]()")))
        except ValueError:
            continue
        if ip not in found:
            found.append(ip)
    return found


def _probes_in(rest: str) -> list[float | None]:
    """Probe results in print order: a float per answered probe, None per
    lost one. ``<1 ms`` (tracert's sub-millisecond marker) becomes 0.5 ms."""
    probes: list[float | None] = []
    for m in _PROBE_RE.finditer(rest):
        if m.group("star"):
            probes.append(None)
            continue
        value = float(m.group("ms").replace(",", "."))
        probes.append(0.5 if m.group("lt") and value <= 1 else value)
    return probes


async def _drain(stream: asyncio.StreamReader, sink: bytearray) -> None:
    while chunk := await stream.read(4096):
        sink.extend(chunk)


async def run_traceroute(
    host: str,
    *,
    max_hops: int = DEFAULT_MAX_HOPS,
    probe_timeout_seconds: float = DEFAULT_PROBE_TIMEOUT_SECONDS,
    overall_timeout_seconds: float | None = None,
) -> TracerouteResult:
    """Runs the platform traceroute and parses it.

    Raises ``TracerouteUnavailable`` if the binary is missing and
    ``ValueError`` for an unsafe host. A run that exceeds the time budget
    does not raise: it returns the hops resolved so far with
    ``timed_out=True``.
    """
    args = build_command(host, max_hops=max_hops, probe_timeout_seconds=probe_timeout_seconds)
    if overall_timeout_seconds is None:
        # Worst case is every probe of every hop timing out.
        overall_timeout_seconds = max_hops * PROBES_PER_HOP * probe_timeout_seconds + 10

    try:
        proc = await asyncio.create_subprocess_exec(
            *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
        )
    except FileNotFoundError as exc:
        raise TracerouteUnavailable(f"{args[0]} is not installed on this system") from exc

    buffer = bytearray()
    timed_out = False
    try:
        assert proc.stdout is not None
        await asyncio.wait_for(_drain(proc.stdout, buffer), timeout=overall_timeout_seconds)
        await asyncio.wait_for(proc.wait(), timeout=5.0)
    except asyncio.TimeoutError:
        timed_out = True
        with suppress(ProcessLookupError):
            proc.kill()
        with suppress(Exception):
            await proc.wait()

    raw = buffer.decode(errors="replace").strip()
    return TracerouteResult(host=host, hops=parse_output(raw), raw=raw, timed_out=timed_out)
