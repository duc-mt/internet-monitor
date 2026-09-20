"""
Latency probing.

Two strategies, matching the brief:

- ICMP: shells out to the system `ping` binary. On virtually every Linux
  distribution `ping` already carries the CAP_NET_RAW capability (or is
  setuid root), so this gets real ICMP echo measurements without our own
  Python process ever touching a raw socket or needing elevated
  privileges itself. We never use shell=True - arguments are passed as a
  list straight to exec, so there is no shell-injection surface even
  though `host` is user-supplied.

- TCP: a plain TCP connect timed end-to-end, used automatically when
  `ping` is missing or blocked (e.g. a locked-down container), or when a
  target is explicitly configured for TCP.

Both return a PingBatchResult so the rest of the app never needs to know
which strategy produced a given measurement.
"""
from __future__ import annotations

import asyncio
import errno
import logging
import re
import shutil
import socket
import sys
import time
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("internet_monitor.pinger")

# Linux (iputils) `ping -W` is a per-reply timeout in *seconds*. macOS/BSD
# ping's `-W` is the same idea but in *milliseconds*. Everything else about
# the invocation (and the output format `_TIME_RE`/`_SUMMARY_RE` parse) is
# close enough between the two that this is the one flag that needs to
# differ by platform.
_IS_BSD_PING = sys.platform == "darwin"

_TIME_RE = re.compile(r"time[=<]\s*([\d.]+)\s*ms")
_SUMMARY_RE = re.compile(
    r"(\d+)\s+packets transmitted,\s+(\d+)\s+(?:packets\s+)?received.*?"
    r"(\d+(?:\.\d+)?)%\s+packet loss",
    re.DOTALL,
)

# Cached once we learn ICMP doesn't work in this environment, so we don't
# retry a doomed subprocess every single check.
_icmp_unavailable: bool | None = None


@dataclass
class PingBatchResult:
    method: str  # "icmp" | "tcp"
    attempted: int
    succeeded: int
    latencies: list[float] = field(default_factory=list)
    error: Optional[str] = None

    @property
    def loss_pct(self) -> float:
        if self.attempted == 0:
            return 100.0
        return round((self.attempted - self.succeeded) / self.attempted * 100, 2)

    @property
    def avg_latency_ms(self) -> Optional[float]:
        if not self.latencies:
            return None
        return round(sum(self.latencies) / len(self.latencies), 2)

    @property
    def jitter_ms(self) -> Optional[float]:
        return compute_jitter(self.latencies)

    @property
    def success(self) -> bool:
        return self.succeeded > 0


def compute_jitter(latencies: list[float]) -> Optional[float]:
    """Mean absolute difference between consecutive samples (RFC-3550-style,
    simplified for a small per-check batch rather than a running average)."""
    if len(latencies) < 2:
        return None
    diffs = [abs(latencies[i] - latencies[i - 1]) for i in range(1, len(latencies))]
    return round(sum(diffs) / len(diffs), 2)


class PingUnavailable(Exception):
    """Raised when ICMP pings cannot be performed in this environment at all."""


def icmp_available() -> bool:
    global _icmp_unavailable
    if _icmp_unavailable is None:
        _icmp_unavailable = shutil.which("ping") is None
    return not _icmp_unavailable


def mark_icmp_unavailable() -> None:
    global _icmp_unavailable
    if not _icmp_unavailable:
        logger.warning(
            "ICMP pings are not available in this environment; "
            "falling back to TCP checks for ICMP-configured targets."
        )
    _icmp_unavailable = True


async def check_icmp(host: str, count: int, timeout: float) -> PingBatchResult:
    if not icmp_available():
        raise PingUnavailable("the 'ping' binary is not installed")

    if _IS_BSD_PING:
        wait_arg = str(max(1, round(timeout * 1000)))  # milliseconds
    else:
        wait_arg = str(max(1, round(timeout)))  # seconds
    args = ["ping", "-n", "-c", str(count), "-W", wait_arg, "--", host]
    overall_timeout = timeout * count + 2.0

    try:
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError:
        mark_icmp_unavailable()
        raise PingUnavailable("the 'ping' binary is not installed")
    except PermissionError:
        mark_icmp_unavailable()
        raise PingUnavailable("not permitted to spawn 'ping' in this environment")

    try:
        stdout_bytes, stderr_bytes = await asyncio.wait_for(proc.communicate(), timeout=overall_timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return PingBatchResult(method="icmp", attempted=count, succeeded=0, error="ping timed out")

    stdout = stdout_bytes.decode(errors="replace")
    stderr = stderr_bytes.decode(errors="replace")
    combined = stdout + stderr

    if "Operation not permitted" in combined or "SOCK_RAW" in combined and "Permission" in combined:
        mark_icmp_unavailable()
        raise PingUnavailable("ICMP sockets are not permitted in this environment")

    latencies = [float(m) for m in _TIME_RE.findall(stdout)]
    summary = _SUMMARY_RE.search(stdout)

    if summary:
        transmitted, received, loss_pct_str = summary.groups()
        attempted = int(transmitted)
        succeeded = int(received)
    else:
        attempted = count
        succeeded = len(latencies)

    error = None
    if succeeded == 0:
        error = _classify_failure(combined)

    return PingBatchResult(method="icmp", attempted=attempted, succeeded=succeeded,
                            latencies=latencies, error=error)


def _classify_failure(combined: str) -> str:
    lowered = combined.lower()
    if "unknown host" in lowered or "name or service not known" in lowered or "temporary failure in name resolution" in lowered:
        return "DNS resolution failed"
    if "network is unreachable" in lowered:
        return "network unreachable"
    if "host unreachable" in lowered or "no route to host" in lowered:
        return "host unreachable"
    if "operation not permitted" in lowered:
        return "ICMP not permitted"
    for line in combined.splitlines():
        line = line.strip()
        if line and not line.startswith("PING "):
            return line[:200]
    return "request timed out"


async def check_tcp(host: str, port: int, count: int, timeout: float) -> PingBatchResult:
    latencies: list[float] = []
    attempted = 0
    last_error: Optional[str] = None

    for _ in range(count):
        attempted += 1
        start = time.monotonic()
        writer = None
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port), timeout=timeout
            )
            elapsed_ms = (time.monotonic() - start) * 1000
            latencies.append(round(elapsed_ms, 2))
        except asyncio.TimeoutError:
            last_error = "connection timed out"
        except OSError as exc:
            last_error = _classify_os_error(exc)
        finally:
            if writer is not None:
                writer.close()
                try:
                    # Bounded wait: a peer that accepts a connection and then
                    # never sends/closes anything must not be able to stall
                    # the monitoring loop indefinitely.
                    await asyncio.wait_for(writer.wait_closed(), timeout=min(timeout, 2.0))
                except (OSError, asyncio.TimeoutError):
                    pass

    succeeded = len(latencies)
    return PingBatchResult(
        method="tcp", attempted=attempted, succeeded=succeeded,
        latencies=latencies, error=last_error if succeeded == 0 else None,
    )


def _classify_os_error(exc: OSError) -> str:
    if isinstance(exc, socket.gaierror):
        return "DNS resolution failed"
    if exc.errno == errno.ECONNREFUSED:
        return "connection refused"
    if exc.errno == errno.EHOSTUNREACH:
        return "host unreachable"
    if exc.errno == errno.ENETUNREACH:
        return "network unreachable"
    return str(exc)[:200]


async def run_check(*, host: str, protocol: str, port: Optional[int], count: int, timeout: float) -> PingBatchResult:
    """Entry point used by the scheduler: picks ICMP or TCP and falls back
    to TCP automatically if ICMP turns out to be unusable."""
    if protocol == "icmp":
        try:
            return await check_icmp(host, count, timeout)
        except PingUnavailable as exc:
            # Fall back silently on success - the fallback itself is already
            # logged once by mark_icmp_unavailable(). Only decorate the
            # error message when the fallback check *also* failed, so a
            # long-running deployment without ICMP access doesn't get this
            # note stamped onto every single successful measurement forever.
            fallback_port = port or 443
            result = await check_tcp(host, fallback_port, count, timeout)
            if result.error:
                result.error = f"ICMP unavailable ({exc}); {result.error}"
            return result
    return await check_tcp(host, port or 443, count, timeout)
