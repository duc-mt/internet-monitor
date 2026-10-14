"""
==============================================================================
Module Name:   burst_prober.py
Description:   Burst Probing engine: 10-20 closely spaced ICMP/TCP probes per
               cycle, RTT measured with perf_counter_ns(), reduced in memory
               to median / IQR / p95 / RFC 3550 jitter / loss.
Author:        Mai Tan Duc <ducmai.network@gmail.com>
Created:       2026-10-14
Version:       1.0.0
License:       MIT
==============================================================================
Usage:         metric = await run_burst(host=..., protocol="icmp", port=None, ...)
Notes:         Linux:   unprivileged ICMP datagram socket, else raw socket
                        (CAP_NET_RAW, e.g. systemd AmbientCapabilities).
               macOS:   unprivileged ICMP datagram socket.
               Windows: IcmpSendEcho2 from iphlpapi.dll through ctypes - no
                        admin rights, no child process.
               TCP:     asyncio.open_connection on every OS.
               If native ICMP is impossible (locked-down container, IPv6-only
               target) it degrades to the old `ping` subprocess, then to TCP.
==============================================================================
"""

from __future__ import annotations

import asyncio
import errno
import ipaddress
import logging
import os
import select
import socket
import struct
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

from app.monitoring import pinger
from app.monitoring.burst_stats import BurstMetric, compute_burst_metric

logger = logging.getLogger("internet_monitor.burst")

# Bounds from the spec; the Settings model enforces the same ones.
MIN_BURST_COUNT = 10
MAX_BURST_COUNT = 20
DEFAULT_BURST_COUNT = 15
MIN_INTERVAL_MS = 15
MAX_INTERVAL_MS = 20
DEFAULT_INTERVAL_MS = 15

# A target that has not answered its first few probes at all is down; waiting a
# full timeout for each of the remaining ones (sequential TCP / Windows probes)
# would stretch one cycle to count x timeout seconds. Remaining probes count as lost.
_GIVE_UP_AFTER_SILENT_PROBES = 3

_ICMP_ECHO_REQUEST = 8
_ICMP_ECHO_REPLY = 0
_PAYLOAD_LEN = 32  # bytes of data per echo request (8-byte random token + filler)

_IS_WINDOWS = sys.platform == "win32"


class ProbeUnavailable(Exception):
    """Native ICMP cannot work here at all (no permission, no raw sockets, no iphlpapi...)."""


class UnsupportedTarget(ProbeUnavailable):
    """Native ICMP works, but not for *this* target (an IPv6 address). Says nothing about the host."""


@dataclass
class ProbeSeries:
    """What a prober hands back: one entry per probe sent, in send order."""

    rtts_ms: list[float | None]
    error: str | None = None


def _ns_to_ms(ns: int) -> float:
    return ns / 1_000_000


# ---------------------------------------------------------------- ICMP packets


def icmp_checksum(data: bytes) -> int:
    """RFC 1071 internet checksum."""
    if len(data) % 2:
        data += b"\x00"
    total = sum(struct.unpack(f"!{len(data) // 2}H", data))
    total = (total >> 16) + (total & 0xFFFF)
    total += total >> 16
    return ~total & 0xFFFF


def build_echo_request(ident: int, seq: int, token: bytes) -> bytes:
    payload = token + bytes(range(_PAYLOAD_LEN - len(token)))
    header = struct.pack("!BBHHH", _ICMP_ECHO_REQUEST, 0, 0, ident & 0xFFFF, seq & 0xFFFF)
    checksum = icmp_checksum(header + payload)
    return struct.pack("!BBHHH", _ICMP_ECHO_REQUEST, 0, checksum, ident & 0xFFFF, seq & 0xFFFF) + payload


def parse_echo_reply(data: bytes, token: bytes, ident: int | None) -> int | None:
    """
    Returns the sequence number if ``data`` is an echo *reply* to one of this
    burst's probes, else None. ``data`` may or may not start with an IPv4
    header (raw sockets and macOS datagram sockets include it, Linux datagram
    sockets do not). The random token in the payload is what ties a reply to
    this burst; the ICMP id is only checked when we chose it ourselves (a Linux
    datagram socket rewrites it with its own).
    """
    if data and (data[0] >> 4) == 4:
        data = data[(data[0] & 0x0F) * 4 :]
    if len(data) < 8 + len(token):
        return None
    icmp_type, code, _checksum, reply_id, seq = struct.unpack("!BBHHH", data[:8])
    if icmp_type != _ICMP_ECHO_REPLY or code != 0:
        return None
    if ident is not None and reply_id != ident:
        return None
    if data[8 : 8 + len(token)] != token:
        return None
    return seq


# --------------------------------------------------------------- name handling


class _NameError(Exception):
    """The host name does not resolve."""


def _resolve_ipv4(host: str) -> str:
    """IPv4 address to probe. Raises _NameError (unresolvable) or ProbeUnavailable (IPv6 only)."""
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    if literal is not None:
        if literal.version == 4:
            return str(literal)
        raise UnsupportedTarget("IPv6 target")
    try:
        infos = socket.getaddrinfo(host, None, socket.AF_INET, socket.SOCK_DGRAM)
    except socket.gaierror:
        try:  # does it exist, but only over IPv6?
            if socket.getaddrinfo(host, None, socket.AF_INET6, socket.SOCK_DGRAM):
                raise UnsupportedTarget("IPv6-only target") from None
        except socket.gaierror:
            pass
        raise _NameError(host) from None
    return str(infos[0][4][0])


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


# ------------------------------------------------- native ICMP: Linux and macOS


def _open_icmp_socket() -> tuple[socket.socket, bool]:
    """
    (socket, we_own_the_icmp_id). Prefers the unprivileged ICMP datagram socket
    (Linux needs net.ipv4.ping_group_range to include the user's group, macOS
    allows it always) and falls back to a raw socket (CAP_NET_RAW / root).
    """
    last_error: OSError | None = None
    for sock_type, owns_id in ((socket.SOCK_DGRAM, False), (socket.SOCK_RAW, True)):
        try:
            return socket.socket(socket.AF_INET, sock_type, socket.IPPROTO_ICMP), owns_id
        except OSError as exc:  # EPERM/EACCES, EPROTONOSUPPORT, EAFNOSUPPORT (containers)...
            last_error = exc
    raise ProbeUnavailable(f"cannot open an ICMP socket ({last_error})")


def _posix_icmp_burst(
    host: str, count: int, interval_s: float, timeout_s: float, cancel: threading.Event
) -> ProbeSeries:
    """
    One burst on a plain blocking-with-select socket, run in a worker thread.
    Probes are sent on a fixed schedule (send i at t0 + i x interval, so the
    spacing does not drift) and replies are collected concurrently, so RTTs
    longer than the interval simply overlap. Each timestamp comes from
    perf_counter_ns(): taken right before sendto() and right after recvfrom().
    """
    try:
        ip = _resolve_ipv4(host)
    except _NameError:
        return ProbeSeries([None] * count, "DNS resolution failed")

    sock, owns_id = _open_icmp_socket()
    try:
        sock.setblocking(False)
        ident = (os.getpid() ^ threading.get_ident()) & 0xFFFF if owns_id else None
        token = os.urandom(8)
        interval_ns = int(interval_s * 1e9)
        timeout_ns = int(timeout_s * 1e9)

        sent_at = [0] * count
        rtts: list[float | None] = [None] * count
        sent = 0
        answered = 0
        send_error: str | None = None
        deadline_ns: int | None = None
        next_send_ns = time.perf_counter_ns()

        while not cancel.is_set():
            now = time.perf_counter_ns()

            if sent < count and now >= next_send_ns:
                packet = build_echo_request(ident if ident is not None else 0, sent, token)
                sent_at[sent] = time.perf_counter_ns()
                try:
                    sock.sendto(packet, (ip, 0))
                except OSError as exc:
                    send_error = _classify_os_error(exc)
                    sent_at[sent] = 0  # never left the machine: cannot be answered
                sent += 1
                next_send_ns += interval_ns
                if sent == count:
                    deadline_ns = time.perf_counter_ns() + timeout_ns
                continue

            if sent == count:
                assert deadline_ns is not None
                if answered >= sum(1 for t in sent_at if t) or now >= deadline_ns:
                    break
                wait_ns = deadline_ns - now
            else:
                wait_ns = next_send_ns - now

            readable, _, _ = select.select([sock], [], [], max(0.0, wait_ns / 1e9))
            if not readable:
                continue
            while True:  # drain everything that is waiting
                try:
                    data, _addr = sock.recvfrom(2048)
                except (BlockingIOError, InterruptedError):
                    break
                except OSError as exc:  # ICMP errors surfaced by the kernel (unreachable...)
                    send_error = send_error or _classify_os_error(exc)
                    break
                received_ns = time.perf_counter_ns()
                seq = parse_echo_reply(data, token, ident)
                if seq is None or seq >= count or rtts[seq] is not None or not sent_at[seq]:
                    continue
                elapsed_ns = received_ns - sent_at[seq]
                if elapsed_ns > timeout_ns:  # per-probe timeout, even though we kept listening
                    continue
                rtts[seq] = _ns_to_ms(elapsed_ns)
                answered += 1

        error = None
        if answered == 0:
            error = send_error or "request timed out"
        return ProbeSeries(rtts, error)
    finally:
        sock.close()


# ----------------------------------------------------- native ICMP: Windows


def _windows_icmp_burst(
    host: str, count: int, interval_s: float, timeout_s: float, cancel: threading.Event
) -> ProbeSeries:
    return _windows_icmp_burst_with(_load_iphlpapi, host, count, interval_s, timeout_s, cancel)


# Status codes from IPTypes.h that are worth naming.
_IP_SUCCESS = 0
_IP_STATUS_TEXT = {
    11002: "network unreachable",
    11003: "host unreachable",
    11004: "protocol unreachable",
    11005: "port unreachable",
    11010: "request timed out",
    11050: "general failure",
}


def _load_iphlpapi():  # pragma: no cover - only meaningful on Windows
    import ctypes

    return ctypes.WinDLL("iphlpapi", use_last_error=True)  # type: ignore[attr-defined]


def _windows_icmp_burst_with(
    load_dll: Callable[[], object],
    host: str,
    count: int,
    interval_s: float,
    timeout_s: float,
    cancel: threading.Event,
) -> ProbeSeries:
    """
    Sequential IcmpSendEcho2 calls (with no event/APC they are synchronous).
    Each RTT is timed with perf_counter_ns() around the call - iphlpapi's own
    RoundTripTime only has whole-millisecond resolution. ``load_dll`` is a
    parameter so the struct handling can be exercised with a stand-in DLL.
    """
    import ctypes
    from ctypes import wintypes

    class IP_OPTION_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("Ttl", ctypes.c_ubyte),
            ("Tos", ctypes.c_ubyte),
            ("Flags", ctypes.c_ubyte),
            ("OptionsSize", ctypes.c_ubyte),
            ("OptionsData", ctypes.c_void_p),
        ]

    class ICMP_ECHO_REPLY(ctypes.Structure):
        _fields_ = [
            ("Address", ctypes.c_uint32),
            ("Status", ctypes.c_uint32),
            ("RoundTripTime", ctypes.c_uint32),
            ("DataSize", ctypes.c_uint16),
            ("Reserved", ctypes.c_uint16),
            ("Data", ctypes.c_void_p),
            ("Options", IP_OPTION_INFORMATION),
        ]

    try:
        ip = _resolve_ipv4(host)
    except _NameError:
        return ProbeSeries([None] * count, "DNS resolution failed")

    try:
        dll = load_dll()
        create_file = dll.IcmpCreateFile  # type: ignore[attr-defined]
        send_echo2 = dll.IcmpSendEcho2  # type: ignore[attr-defined]
        close_handle = dll.IcmpCloseHandle  # type: ignore[attr-defined]
        create_file.restype = wintypes.HANDLE
        create_file.argtypes = []
        send_echo2.restype = wintypes.DWORD
        send_echo2.argtypes = [
            wintypes.HANDLE,  # IcmpHandle
            wintypes.HANDLE,  # Event (NULL => synchronous)
            ctypes.c_void_p,  # ApcRoutine (NULL)
            ctypes.c_void_p,  # ApcContext (NULL)
            ctypes.c_uint32,  # DestinationAddress (network byte order)
            ctypes.c_char_p,  # RequestData
            wintypes.WORD,  # RequestSize
            ctypes.c_void_p,  # RequestOptions (NULL)
            ctypes.c_void_p,  # ReplyBuffer
            wintypes.DWORD,  # ReplySize
            wintypes.DWORD,  # Timeout (ms)
        ]
        close_handle.argtypes = [wintypes.HANDLE]
    except (OSError, AttributeError) as exc:
        raise ProbeUnavailable(f"iphlpapi.dll is not usable ({exc})") from exc

    handle = create_file()
    if not handle or handle == ctypes.c_void_p(-1).value:
        raise ProbeUnavailable("IcmpCreateFile failed")

    dest = int.from_bytes(socket.inet_aton(ip), "little")  # IPAddr: bytes a.b.c.d in memory
    payload = bytes(range(_PAYLOAD_LEN))
    reply_size = ctypes.sizeof(ICMP_ECHO_REPLY) + len(payload) + 8 + 64
    reply_buf = ctypes.create_string_buffer(reply_size)
    timeout_ms = max(1, int(timeout_s * 1000))
    interval_ns = int(interval_s * 1e9)

    rtts: list[float | None] = []
    last_status: int | None = None
    silent_run = 0
    try:
        next_slot_ns = time.perf_counter_ns()
        for _ in range(count):
            if cancel.is_set():
                break
            if rtts and not any(r is not None for r in rtts) and silent_run >= _GIVE_UP_AFTER_SILENT_PROBES:
                break  # target is not answering at all - do not wait out the rest
            wait_ns = next_slot_ns - time.perf_counter_ns()
            if wait_ns > 0:
                time.sleep(wait_ns / 1e9)

            started = time.perf_counter_ns()
            replies = send_echo2(
                handle, None, None, None, dest, payload, len(payload), None, reply_buf, reply_size, timeout_ms
            )
            elapsed = time.perf_counter_ns() - started
            status = ICMP_ECHO_REPLY.from_buffer(reply_buf).Status if replies else None
            if replies and status == _IP_SUCCESS:
                rtts.append(_ns_to_ms(elapsed))
                silent_run = 0
            else:
                rtts.append(None)
                silent_run += 1
                last_status = status if status is not None else last_status
            next_slot_ns = started + interval_ns
        rtts.extend([None] * (count - len(rtts)))  # abandoned probes count as lost
    finally:
        close_handle(handle)

    error = None
    if not any(r is not None for r in rtts):
        error = _IP_STATUS_TEXT.get(last_status or 11010, f"ICMP status {last_status}")
    return ProbeSeries(rtts, error)


# ------------------------------------------------------------------------ TCP


async def probe_tcp(host: str, port: int, count: int, interval_s: float, timeout_s: float) -> ProbeSeries:
    """
    ``count`` sequential TCP handshakes. The name is resolved once up front so
    DNS time is not folded into every RTT; the clock is perf_counter_ns() around
    asyncio.open_connection() only.
    """
    loop = asyncio.get_running_loop()
    try:
        infos = await asyncio.wait_for(loop.getaddrinfo(host, port, type=socket.SOCK_STREAM), timeout=timeout_s)
        address = str(infos[0][4][0])
    except (socket.gaierror, asyncio.TimeoutError, IndexError):
        return ProbeSeries([None] * count, "DNS resolution failed")

    rtts: list[float | None] = []
    last_error: str | None = None
    for i in range(count):
        if not any(r is not None for r in rtts) and len(rtts) >= _GIVE_UP_AFTER_SILENT_PROBES:
            break  # nothing answered the first few probes: the target is down
        if i and interval_s > 0:
            await asyncio.sleep(interval_s)
        writer = None
        started = time.perf_counter_ns()
        try:
            _reader, writer = await asyncio.wait_for(asyncio.open_connection(address, port), timeout=timeout_s)
            rtts.append(_ns_to_ms(time.perf_counter_ns() - started))
        except asyncio.TimeoutError:
            rtts.append(None)
            last_error = "connection timed out"
        except OSError as exc:
            rtts.append(None)
            last_error = _classify_os_error(exc)
        finally:
            if writer is not None:
                writer.close()
                try:
                    # A peer that accepts and then never closes must not stall the cycle.
                    await asyncio.wait_for(writer.wait_closed(), timeout=min(timeout_s, 2.0))
                except (OSError, asyncio.TimeoutError):
                    pass
    rtts.extend([None] * (count - len(rtts)))
    return ProbeSeries(rtts, None if any(r is not None for r in rtts) else last_error)


# --------------------------------------------------------------- orchestration

# None = not tried yet, True = native ICMP works here, False = it does not (do not retry every cycle).
_native_icmp_ok: bool | None = None


def _icmp_engine() -> str:
    """INTERNET_MONITOR_ICMP_ENGINE: "auto" (default) tries native ICMP first; "ping" skips it and uses the
    system `ping` command exactly as before Burst Probing - an escape hatch for an unusual platform."""
    return os.environ.get("INTERNET_MONITOR_ICMP_ENGINE", "auto").strip().lower()


def reset_state() -> None:
    """Used by tests."""
    global _native_icmp_ok
    _native_icmp_ok = None


def _native_icmp_burst(
    host: str, count: int, interval_s: float, timeout_s: float, cancel: threading.Event
) -> ProbeSeries:
    if _IS_WINDOWS:
        return _windows_icmp_burst(host, count, interval_s, timeout_s, cancel)
    return _posix_icmp_burst(host, count, interval_s, timeout_s, cancel)


async def _run_native_icmp(host: str, count: int, interval_s: float, timeout_s: float) -> ProbeSeries:
    cancel = threading.Event()
    try:
        # In a worker thread: the schedule is timed to the millisecond and must
        # not be delayed by whatever else is running on the event loop.
        return await asyncio.to_thread(_native_icmp_burst, host, count, interval_s, timeout_s, cancel)
    except asyncio.CancelledError:
        cancel.set()  # let the thread stop sending at its next step
        raise


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


async def run_burst(
    *, host: str, protocol: str, port: int | None, count: int, interval_ms: float, timeout: float
) -> BurstMetric:
    """
    One Burst Probing cycle for one target. Always returns a BurstMetric (a dead
    target is simply 100 % loss); it only raises on cancellation or a bug.
    """
    global _native_icmp_ok
    interval_s = _clamp(interval_ms, MIN_INTERVAL_MS, MAX_INTERVAL_MS) / 1000

    if protocol == "icmp" and _icmp_engine() != "ping" and _native_icmp_ok is not False:
        try:
            series = await _run_native_icmp(host, count, interval_s, timeout)
        except UnsupportedTarget:
            pass  # e.g. an IPv6 literal: use the legacy path for this target only
        except ProbeUnavailable as exc:
            logger.warning("Native ICMP is unavailable (%s); falling back to the `ping` command / TCP checks", exc)
            _native_icmp_ok = False
        except Exception:
            # A surprise inside the native path (an OS quirk, a ctypes mismatch) must never stop
            # monitoring: log it once, and use the `ping` command for the rest of this process.
            logger.exception("Native ICMP failed unexpectedly; falling back to the `ping` command / TCP checks")
            _native_icmp_ok = False
        else:
            _native_icmp_ok = True
            return compute_burst_metric(series.rtts_ms, method="icmp", error=series.error)

    if protocol == "icmp":
        # Degraded mode: the system `ping` (then TCP), exactly as before the upgrade. No 15 ms
        # pacing is possible this way, but it still yields a real burst of samples.
        legacy = await pinger.run_check(host=host, protocol="icmp", port=port, count=count, timeout=timeout)
        return _from_legacy(legacy)

    series = await probe_tcp(host, port or 443, count, interval_s, timeout)
    return compute_burst_metric(series.rtts_ms, method="tcp", error=series.error)


def _from_legacy(result: pinger.PingBatchResult) -> BurstMetric:
    lost = max(0, result.attempted - result.succeeded)
    rtts: list[float | None] = [*result.latencies, *([None] * lost)]
    if not rtts:  # attempted == 0: cannot happen with count >= 1, but never divide by zero
        rtts = [None]
    return compute_burst_metric(rtts, method=result.method, error=result.error)
