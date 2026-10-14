"""
==============================================================================
Module Name:   test_burst_prober.py
Description:   Burst prober: ICMP packet codec, fake-socket bursts, TCP bursts, fallbacks, Windows struct handling.
Author:        Mai Tan Duc <ducmai.network@gmail.com>
Created:       2026-10-14
Version:       1.0.0
License:       MIT
==============================================================================
Usage:         pytest backend/tests/test_burst_prober.py
Notes:         See module docstrings of the code under test.
==============================================================================
"""

from __future__ import annotations

import asyncio
import ctypes
import os
import socket
import struct
import threading
import time

import pytest
from app.monitoring import burst_prober as bp
from app.monitoring import pinger


@pytest.fixture(autouse=True)
def _fresh_state():
    bp.reset_state()
    yield
    bp.reset_state()


# ---------------------------------------------------------------- packet codec


def test_checksum_of_a_correct_packet_is_zero():
    packet = bp.build_echo_request(0x1234, 7, b"TOKEN123")
    assert bp.icmp_checksum(packet) == 0  # RFC 1071: summing a valid packet incl. its checksum folds to 0


def test_build_echo_request_layout():
    packet = bp.build_echo_request(0xBEEF, 3, b"ABCDEFGH")
    icmp_type, code, _ck, ident, seq = struct.unpack("!BBHHH", packet[:8])
    assert (icmp_type, code, ident, seq) == (8, 0, 0xBEEF, 3)
    assert packet[8:16] == b"ABCDEFGH"
    assert len(packet) == 8 + 32


def _reply_to(request: bytes, *, with_ip_header: bool, ident: int | None = None) -> bytes:
    """What the network sends back: same id/seq/payload, type 0."""
    _t, _c, _ck, rid, seq = struct.unpack("!BBHHH", request[:8])
    icmp = struct.pack("!BBHHH", 0, 0, 0, rid if ident is None else ident, seq) + request[8:]
    return (b"\x45" + b"\x00" * 19 + icmp) if with_ip_header else icmp


@pytest.mark.parametrize("with_ip_header", [False, True])
def test_parse_echo_reply_accepts_both_framings(with_ip_header):
    token = b"TOKEN123"
    request = bp.build_echo_request(0x1111, 5, token)
    assert bp.parse_echo_reply(_reply_to(request, with_ip_header=with_ip_header), token, ident=0x1111) == 5


def test_parse_echo_reply_rejects_foreign_traffic():
    token = b"TOKEN123"
    request = bp.build_echo_request(0x1111, 5, token)
    reply = _reply_to(request, with_ip_header=False)
    assert bp.parse_echo_reply(reply, b"OTHERTOK", ident=0x1111) is None  # someone else's ping
    assert bp.parse_echo_reply(_reply_to(request, with_ip_header=False, ident=0x2222), token, ident=0x1111) is None
    assert bp.parse_echo_reply(reply, token, ident=None) == 5  # datagram sockets: id is the kernel's, not checked
    assert bp.parse_echo_reply(request, token, ident=None) is None  # an echo *request* (type 8), not a reply
    assert bp.parse_echo_reply(b"\x00\x01", token, ident=None) is None  # truncated


# ------------------------------------------------ the scheduled burst, fake socket


class _FakeIcmpSocket:
    """A socket that 'answers' echo requests after a configurable delay, in memory."""

    def __init__(self, delays_ms: dict[int, float | None], *, ip_header: bool = False, noise: bool = False):
        self.delays_ms = delays_ms  # seq -> reply delay (None = never answered)
        self.ip_header = ip_header
        self.noise = noise
        self.closed = False
        self._r, self._w = socket.socketpair()
        self._r.setblocking(False)
        self.sent: list[int] = []
        self.send_times: list[float] = []
        self._timers: list[threading.Timer] = []

    def setblocking(self, flag):
        pass

    def fileno(self):
        return self._r.fileno()

    def sendto(self, packet, addr):
        _t, _c, _ck, _id, seq = struct.unpack("!BBHHH", packet[:8])
        self.sent.append(seq)
        self.send_times.append(time.perf_counter())
        reply = _reply_to(packet, with_ip_header=self.ip_header)
        if self.noise:  # a foreign echo reply that must be ignored
            self._w.send(_reply_to(bp.build_echo_request(1, seq, b"NOTOURS!"), with_ip_header=self.ip_header))
        delay = self.delays_ms.get(seq, 1.0)
        if delay is not None:
            timer = threading.Timer(delay / 1000, lambda: self._w.send(reply))
            timer.start()
            self._timers.append(timer)

    def recvfrom(self, n):
        return self._r.recv(n), ("127.0.0.1", 0)

    def close(self):
        self.closed = True
        for t in self._timers:
            t.cancel()
        self._r.close()
        self._w.close()


@pytest.fixture
def fake_socket(monkeypatch):
    holder: dict = {}

    def install(sock: _FakeIcmpSocket, owns_id: bool = False):
        holder["sock"] = sock
        monkeypatch.setattr(bp, "_open_icmp_socket", lambda: (sock, owns_id))
        monkeypatch.setattr(bp, "_resolve_ipv4", lambda host: "203.0.113.9")
        return sock

    return install


def test_posix_burst_measures_each_probe_and_marks_the_lost_ones(fake_socket):
    delays = {i: 5.0 + i for i in range(10)}
    delays[3] = None  # lost
    delays[7] = None  # lost
    sock = fake_socket(_FakeIcmpSocket(delays))
    series = bp._posix_icmp_burst("example.test", 10, 0.015, 0.5, threading.Event())

    assert sock.sent == list(range(10)) and sock.closed
    assert series.error is None
    assert [r is None for r in series.rtts_ms] == [i in (3, 7) for i in range(10)]
    for i, rtt in enumerate(series.rtts_ms):
        if rtt is not None:  # perf_counter_ns-based, so should track the injected delay
            assert delays[i] <= rtt < delays[i] + 25, (i, rtt)


def test_posix_burst_paces_probes_on_a_fixed_schedule(fake_socket):
    sock = fake_socket(_FakeIcmpSocket({i: 1.0 for i in range(10)}))
    bp._posix_icmp_burst("example.test", 10, 0.020, 0.5, threading.Event())
    gaps = [b - a for a, b in zip(sock.send_times, sock.send_times[1:])]
    assert 0.015 < sum(gaps) / len(gaps) < 0.030  # ~20 ms apart, no drift
    assert sock.send_times[-1] - sock.send_times[0] < 0.4  # the whole burst well inside 400 ms


def test_posix_burst_ignores_foreign_replies_and_handles_ip_headers(fake_socket):
    fake_socket(_FakeIcmpSocket({i: 2.0 for i in range(10)}, ip_header=True, noise=True))
    series = bp._posix_icmp_burst("example.test", 10, 0.015, 0.5, threading.Event())
    assert all(r is not None for r in series.rtts_ms)


def test_posix_burst_all_lost_reports_timeout(fake_socket):
    fake_socket(_FakeIcmpSocket({i: None for i in range(10)}))
    started = time.perf_counter()
    series = bp._posix_icmp_burst("example.test", 10, 0.015, 0.3, threading.Event())
    assert series.rtts_ms == [None] * 10
    assert series.error == "request timed out"
    assert time.perf_counter() - started < 1.0  # waited ~timeout after the last send, not 10 x timeout


def test_posix_burst_enforces_the_per_probe_timeout(fake_socket):
    # probe 0 is answered after 400 ms, which is later than the 150 ms timeout, though we are still listening
    fake_socket(_FakeIcmpSocket({0: 400.0, **{i: 1.0 for i in range(1, 10)}}))
    series = bp._posix_icmp_burst("example.test", 10, 0.015, 0.15, threading.Event())
    assert series.rtts_ms[0] is None
    assert all(r is not None for r in series.rtts_ms[1:])


def test_posix_burst_cancellation_stops_sending(fake_socket):
    sock = fake_socket(_FakeIcmpSocket({}))
    cancel = threading.Event()
    cancel.set()
    series = bp._posix_icmp_burst("example.test", 10, 0.015, 0.5, cancel)
    assert sock.sent == [] and sock.closed
    assert series.rtts_ms == [None] * 10


def test_posix_burst_dns_failure_is_loss_not_unavailable(monkeypatch):
    def boom(host):
        raise bp._NameError(host)

    monkeypatch.setattr(bp, "_resolve_ipv4", boom)
    series = bp._posix_icmp_burst("nope.invalid", 10, 0.015, 0.5, threading.Event())
    assert series.rtts_ms == [None] * 10 and series.error == "DNS resolution failed"


def test_open_icmp_socket_unavailable_without_permission(monkeypatch):
    def deny(*args, **kwargs):
        raise PermissionError(13, "Operation not permitted")

    monkeypatch.setattr(bp.socket, "socket", deny)
    with pytest.raises(bp.ProbeUnavailable):
        bp._open_icmp_socket()


def test_resolve_ipv4_handles_literals():
    assert bp._resolve_ipv4("8.8.8.8") == "8.8.8.8"
    with pytest.raises(bp.UnsupportedTarget):
        bp._resolve_ipv4("2001:4860:4860::8888")


@pytest.mark.skipif(
    not hasattr(os, "geteuid") or os.geteuid() != 0, reason="needs a raw/ping socket; only asserted when privileged"
)
def test_real_icmp_burst_against_loopback():
    try:
        sock, _ = bp._open_icmp_socket()
        sock.close()
    except bp.ProbeUnavailable:
        pytest.skip("no ICMP socket available here")
    series = bp._posix_icmp_burst("127.0.0.1", 10, 0.015, 1.0, threading.Event())
    assert all(r is not None and 0 < r < 50 for r in series.rtts_ms)


# ------------------------------------------------------------------------ TCP


async def test_tcp_burst_against_a_local_listener():
    async def handle(reader, writer):
        writer.close()

    server = await asyncio.start_server(handle, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    try:
        series = await bp.probe_tcp("127.0.0.1", port, 10, 0.0, 1.0)
    finally:
        server.close()
        await server.wait_closed()
    assert len(series.rtts_ms) == 10 and all(r is not None and r > 0 for r in series.rtts_ms)
    assert series.error is None


async def test_tcp_burst_gives_up_early_on_a_dead_port():
    # an unused port: connections are refused immediately
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    started = time.perf_counter()
    series = await bp.probe_tcp("127.0.0.1", port, 15, 0.02, 1.0)
    assert series.rtts_ms == [None] * 15  # abandoned probes count as lost
    assert series.error == "connection refused"
    assert time.perf_counter() - started < 0.5


async def test_tcp_burst_dns_failure():
    series = await bp.probe_tcp("no-such-host.invalid", 443, 10, 0.0, 1.0)
    assert series.rtts_ms == [None] * 10 and series.error == "DNS resolution failed"


# ------------------------------------------------------------- orchestration


async def test_run_burst_reduces_a_native_series(monkeypatch):
    async def fake_native(host, count, interval_s, timeout_s):
        return bp.ProbeSeries([float(10 + i) for i in range(count)])

    monkeypatch.setattr(bp, "_run_native_icmp", fake_native)
    m = await bp.run_burst(host="x", protocol="icmp", port=None, count=15, interval_ms=20, timeout=1.0)
    assert (m.method, m.packet_count, m.loss_percent, m.median_rtt) == ("icmp", 15, 0.0, 17.0)


async def test_run_burst_clamps_the_interval(monkeypatch):
    seen = {}

    async def fake_native(host, count, interval_s, timeout_s):
        seen["interval_s"] = interval_s
        return bp.ProbeSeries([1.0] * count)

    monkeypatch.setattr(bp, "_run_native_icmp", fake_native)
    await bp.run_burst(host="x", protocol="icmp", port=None, count=10, interval_ms=1, timeout=1.0)
    assert seen["interval_s"] == 0.015
    await bp.run_burst(host="x", protocol="icmp", port=None, count=10, interval_ms=500, timeout=1.0)
    assert seen["interval_s"] == 0.020


async def test_run_burst_falls_back_to_the_ping_command_and_remembers(monkeypatch, caplog):
    native_calls = 0

    async def no_native(host, count, interval_s, timeout_s):
        nonlocal native_calls
        native_calls += 1
        raise bp.ProbeUnavailable("cannot open an ICMP socket (denied)")

    async def fake_run_check(*, host, protocol, port, count, timeout):
        return pinger.PingBatchResult(
            method="icmp", attempted=count, succeeded=count - 2, latencies=[10.0 + i for i in range(count - 2)]
        )

    monkeypatch.setattr(bp, "_run_native_icmp", no_native)
    monkeypatch.setattr(bp.pinger, "run_check", fake_run_check)

    with caplog.at_level("WARNING", logger="internet_monitor.burst"):
        first = await bp.run_burst(host="x", protocol="icmp", port=None, count=12, interval_ms=20, timeout=1.0)
        second = await bp.run_burst(host="x", protocol="icmp", port=None, count=12, interval_ms=20, timeout=1.0)

    assert native_calls == 1  # not re-tried on every cycle
    assert sum("Native ICMP is unavailable" in r.message for r in caplog.records) == 1
    assert first.packet_count == 12 and first.received == 10 and round(first.loss_percent, 2) == 16.67
    assert second.median_rtt is not None


async def test_run_burst_survives_an_unexpected_native_failure(monkeypatch, caplog):
    calls = 0

    async def broken(host, count, interval_s, timeout_s):
        nonlocal calls
        calls += 1
        raise RuntimeError("ctypes mismatch")

    async def fake_run_check(*, host, protocol, port, count, timeout):
        return pinger.PingBatchResult(method="icmp", attempted=count, succeeded=count, latencies=[7.0] * count)

    monkeypatch.setattr(bp, "_run_native_icmp", broken)
    monkeypatch.setattr(bp.pinger, "run_check", fake_run_check)
    with caplog.at_level("ERROR", logger="internet_monitor.burst"):
        first = await bp.run_burst(host="x", protocol="icmp", port=None, count=10, interval_ms=20, timeout=1.0)
        second = await bp.run_burst(host="x", protocol="icmp", port=None, count=10, interval_ms=20, timeout=1.0)
    assert first.success and second.success and first.median_rtt == 7.0
    assert calls == 1  # not retried every cycle
    assert sum("Native ICMP failed unexpectedly" in r.message for r in caplog.records) == 1


async def test_icmp_engine_env_override_forces_the_ping_command(monkeypatch):
    async def native(host, count, interval_s, timeout_s):
        raise AssertionError("native ICMP must not be used when INTERNET_MONITOR_ICMP_ENGINE=ping")

    async def fake_run_check(*, host, protocol, port, count, timeout):
        return pinger.PingBatchResult(method="icmp", attempted=count, succeeded=count, latencies=[9.0] * count)

    monkeypatch.setattr(bp, "_run_native_icmp", native)
    monkeypatch.setattr(bp.pinger, "run_check", fake_run_check)
    monkeypatch.setenv("INTERNET_MONITOR_ICMP_ENGINE", "ping")
    m = await bp.run_burst(host="x", protocol="icmp", port=None, count=10, interval_ms=20, timeout=1.0)
    assert m.median_rtt == 9.0


async def test_run_burst_ipv6_target_uses_legacy_path_without_disabling_native(monkeypatch):
    async def v6(host, count, interval_s, timeout_s):
        raise bp.UnsupportedTarget("IPv6 target")

    async def fake_run_check(*, host, protocol, port, count, timeout):
        return pinger.PingBatchResult(method="icmp", attempted=count, succeeded=count, latencies=[5.0] * count)

    monkeypatch.setattr(bp, "_run_native_icmp", v6)
    monkeypatch.setattr(bp.pinger, "run_check", fake_run_check)
    m = await bp.run_burst(host="::1", protocol="icmp", port=None, count=10, interval_ms=20, timeout=1.0)
    assert m.success and bp._native_icmp_ok is None  # IPv6 says nothing about IPv4 support


async def test_run_burst_tcp_path(monkeypatch):
    async def fake_tcp(host, port, count, interval_s, timeout_s):
        assert port == 8443
        return bp.ProbeSeries([float(i + 1) for i in range(count)])

    monkeypatch.setattr(bp, "probe_tcp", fake_tcp)
    m = await bp.run_burst(host="x", protocol="tcp", port=8443, count=10, interval_ms=20, timeout=1.0)
    assert m.method == "tcp" and m.median_rtt == 5.5


async def test_cancelling_a_native_burst_signals_the_worker_thread(monkeypatch):
    seen = {}

    def slow(host, count, interval_s, timeout_s, cancel):
        seen["cancel"] = cancel
        cancel.wait(2.0)
        return bp.ProbeSeries([None] * count)

    monkeypatch.setattr(bp, "_native_icmp_burst", slow)
    task = asyncio.create_task(bp._run_native_icmp("x", 10, 0.02, 1.0))
    await asyncio.sleep(0.1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert seen["cancel"].is_set()


# ----------------------------------------------- Windows (iphlpapi) code path
# These run on every OS with a stand-in for iphlpapi.dll: they prove the struct layout
# handling and the control flow, NOT that real Windows behaves this way.


class _FakeIphlpapi:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)  # per call: None = timeout, or an IP status code (0 = success)
        self.calls = 0
        self.closed = False
        self.dest_seen = None

    class _Fn:
        def __init__(self, fn):
            self.fn = fn
            self.restype = None
            self.argtypes = None

        def __call__(self, *a):
            return self.fn(*a)

    def __getattr__(self, name):
        if name == "IcmpCreateFile":
            return self._Fn(lambda: 1234)
        if name == "IcmpCloseHandle":
            return self._Fn(lambda h: setattr(self, "closed", True) or 1)
        if name == "IcmpSendEcho2":
            return self._Fn(self._send)
        raise AttributeError(name)

    def _send(self, handle, event, apc, ctx, dest, data, size, opts, reply_buf, reply_size, timeout_ms):
        self.dest_seen = dest
        outcome = self.outcomes[min(self.calls, len(self.outcomes) - 1)]
        self.calls += 1
        time.sleep(0.002)
        if outcome is None:
            return 0
        # ICMP_ECHO_REPLY.Status lives at byte offset 4 (after the 4-byte Address)
        struct.pack_into("<I", reply_buf, 4, outcome)
        return 1


def test_windows_burst_times_calls_and_marks_failures(monkeypatch):
    monkeypatch.setattr(bp, "_resolve_ipv4", lambda h: "192.0.2.10")
    dll = _FakeIphlpapi([0, 0, None, 0, 11003, 0, 0, 0, 0, 0])
    series = bp._windows_icmp_burst_with(lambda: dll, "x", 10, 0.015, 0.5, threading.Event())
    assert dll.calls == 10 and dll.closed
    assert [r is None for r in series.rtts_ms] == [False, False, True, False, True] + [False] * 5
    assert all(r is None or 1.0 < r < 100 for r in series.rtts_ms)
    # 192.0.2.10 as an IPAddr: bytes c0 00 02 0a in memory -> little-endian int
    assert dll.dest_seen == int.from_bytes(bytes([192, 0, 2, 10]), "little")


def test_windows_burst_gives_up_on_a_silent_target(monkeypatch):
    monkeypatch.setattr(bp, "_resolve_ipv4", lambda h: "192.0.2.10")
    dll = _FakeIphlpapi([None])  # never answers
    series = bp._windows_icmp_burst_with(lambda: dll, "x", 15, 0.015, 0.5, threading.Event())
    assert dll.calls == 3  # stopped after the first silent probes instead of waiting out all 15
    assert series.rtts_ms == [None] * 15
    assert series.error == "request timed out"


def test_windows_burst_dll_failure_means_unavailable(monkeypatch):
    monkeypatch.setattr(bp, "_resolve_ipv4", lambda h: "192.0.2.10")

    def no_dll():
        raise OSError("iphlpapi.dll not found")

    with pytest.raises(bp.ProbeUnavailable):
        bp._windows_icmp_burst_with(no_dll, "x", 10, 0.015, 0.5, threading.Event())


def test_icmp_echo_reply_struct_matches_the_documented_layout():
    # ICMP_ECHO_REPLY on 64-bit Windows: 4+4+4+2+2 = 16, pad to 8, Data ptr (8), IP_OPTION_INFORMATION (4 + pad + 8 = 16)
    # The struct is declared inside the function; rebuild it the same way to check the Status offset used above.
    class Opt(ctypes.Structure):
        _fields_ = [
            ("Ttl", ctypes.c_ubyte),
            ("Tos", ctypes.c_ubyte),
            ("Flags", ctypes.c_ubyte),
            ("OptionsSize", ctypes.c_ubyte),
            ("OptionsData", ctypes.c_void_p),
        ]

    class Reply(ctypes.Structure):
        _fields_ = [
            ("Address", ctypes.c_uint32),
            ("Status", ctypes.c_uint32),
            ("RoundTripTime", ctypes.c_uint32),
            ("DataSize", ctypes.c_uint16),
            ("Reserved", ctypes.c_uint16),
            ("Data", ctypes.c_void_p),
            ("Options", Opt),
        ]

    assert Reply.Status.offset == 4
    if ctypes.sizeof(ctypes.c_void_p) == 8:
        assert ctypes.sizeof(Reply) == 40
