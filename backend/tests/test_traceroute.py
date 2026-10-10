from __future__ import annotations

"""
==============================================================================
Module Name:   test_traceroute.py
Description:   Implementation and logic for test_traceroute.
Author:        Mai Tan Duc <ducmai.network@gmail.com>
Created:       2026-10-10
Version:       1.0.0
License:       MIT
==============================================================================
Usage:         python3 test_traceroute.py [options]
Notes:         Requires Python 3.8+
==============================================================================
"""

import asyncio

import pytest
from app.monitoring import traceroute as tr

# All addresses below are dummy data: RFC 1918 / RFC 6598 ranges and public
# DNS resolvers, never real hosts.
LINUX_OUTPUT = """traceroute to 1.1.1.1 (1.1.1.1), 15 hops max, 60 byte packets
 1  192.168.1.1  0.523 ms  0.490 ms  0.480 ms
 2  * * *
 3  100.64.0.1  5.1 ms  5.3 ms *
 4  1.1.1.1  9.8 ms  9.9 ms  10.1 ms
"""

WINDOWS_OUTPUT = """
Tracing route to 1.1.1.1 over a maximum of 15 hops

  1    <1 ms    <1 ms    <1 ms  192.168.1.1
  2     *        *        *     Request timed out.
  3     5 ms     5 ms     6 ms  10.20.0.1
  4    12 ms    11 ms    12 ms  1.1.1.1

Trace complete.
"""


def test_parse_linux_output():
    hops = tr.parse_output(LINUX_OUTPUT)
    assert [h.hop for h in hops] == [1, 2, 3, 4]
    assert hops[0].address == "192.168.1.1"
    assert hops[0].rtts_ms == [0.523, 0.49, 0.48]
    assert hops[0].scope == "private"
    assert hops[1].address is None
    assert hops[1].rtts_ms == [None, None, None]
    assert hops[2].scope == "cgnat"
    assert hops[2].rtts_ms == [5.1, 5.3, None]
    assert hops[3].address == "1.1.1.1"
    assert hops[3].scope == "public"


def test_parse_windows_output_handles_sub_millisecond_replies_and_timeouts():
    hops = tr.parse_output(WINDOWS_OUTPUT)
    assert [h.hop for h in hops] == [1, 2, 3, 4]
    assert hops[0].rtts_ms == [0.5, 0.5, 0.5]  # "<1 ms"
    assert hops[1].address is None
    assert hops[1].rtts_ms == [None, None, None]
    assert hops[2].rtts_ms == [5.0, 5.0, 6.0]
    assert hops[3].address == "1.1.1.1"


def test_parse_does_not_depend_on_the_language_of_the_timeout_message():
    german = "  2     *        *        *     Zeit\u00fcberschreitung der Anforderung.\n"
    (hop,) = tr.parse_output(german)
    assert hop.hop == 2 and hop.address is None and hop.rtts_ms == [None, None, None]


def test_parse_hop_with_several_addresses_keeps_the_first_and_lists_the_rest():
    (hop,) = tr.parse_output(" 4  10.0.0.2  1.0 ms 10.0.0.3  2.0 ms  1.5 ms\n")
    assert hop.address == "10.0.0.2"
    assert hop.extra_addresses == ["10.0.0.3"]
    assert hop.rtts_ms == [1.0, 2.0, 1.5]


def test_parse_ignores_headers_footers_and_blank_lines():
    assert tr.parse_output("") == []
    assert tr.parse_output("traceroute to 1.1.1.1 (1.1.1.1), 15 hops max\n\nTrace complete.\n") == []


def test_parse_handles_hostname_with_bracketed_address():
    (hop,) = tr.parse_output("  3    12 ms    11 ms    12 ms  router.example.net [10.1.2.3]\n")
    assert hop.address == "10.1.2.3"


def test_parse_ipv6_address():
    (hop,) = tr.parse_output(" 1  fe80::1  0.4 ms  0.5 ms  0.6 ms\n")
    assert hop.address == "fe80::1"
    assert hop.scope == "private"


@pytest.mark.parametrize(
    ("address", "scope"),
    [
        ("192.168.0.1", "private"),
        ("10.0.0.1", "private"),
        ("172.16.5.5", "private"),
        ("100.64.12.1", "cgnat"),
        ("100.127.255.254", "cgnat"),
        ("1.1.1.1", "public"),
        ("8.8.8.8", "public"),
        (None, "unknown"),
        ("not-an-ip", "unknown"),
    ],
)
def test_classify_address(address, scope):
    assert tr.classify_address(address) == scope


def test_hop_average_and_loss():
    hop = tr.Hop(hop=1, address="10.0.0.1", rtts_ms=[1.0, 2.0, None])
    assert hop.avg_ms == 1.5
    assert hop.loss_pct == 33.3
    silent = tr.Hop(hop=2, address=None, rtts_ms=[None, None, None])
    assert silent.avg_ms is None
    assert silent.loss_pct == 100.0


def test_build_command_unix_ends_option_parsing_before_the_host():
    cmd = tr.build_command("1.1.1.1", windows=False)
    assert cmd[0] == "traceroute"
    assert "-n" in cmd  # no reverse DNS on a path that may be dropping packets
    assert cmd[-2:] == ["--", "1.1.1.1"]


def test_build_command_windows_uses_tracert_with_millisecond_timeout():
    cmd = tr.build_command("1.1.1.1", max_hops=10, probe_timeout_seconds=2, windows=True)
    assert cmd == ["tracert", "-d", "-h", "10", "-w", "2000", "1.1.1.1"]


@pytest.mark.parametrize("bad", ["", "   ", "-oProxyCommand=x", "--help", "a b", "1.1.1.1\n-x"])
def test_build_command_rejects_unsafe_hosts(bad):
    with pytest.raises(ValueError):
        tr.build_command(bad, windows=False)


class _FakeStream:
    def __init__(self, chunks: list[bytes], *, hang_after: bool = False):
        self._chunks = list(chunks)
        self._hang_after = hang_after

    async def read(self, _n: int) -> bytes:
        if self._chunks:
            return self._chunks.pop(0)
        if self._hang_after:
            await asyncio.sleep(3600)  # traceroute still waiting on later hops
        return b""


class _FakeProc:
    def __init__(self, stream: _FakeStream):
        self.stdout = stream
        self.killed = False

    async def wait(self) -> int:
        return 0

    def kill(self) -> None:
        self.killed = True


@pytest.mark.asyncio
async def test_run_traceroute_parses_process_output(monkeypatch):
    async def fake_exec(*args, **kwargs):
        return _FakeProc(_FakeStream([LINUX_OUTPUT.encode()]))

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    result = await tr.run_traceroute("1.1.1.1")
    assert result.host == "1.1.1.1"
    assert result.timed_out is False
    assert [h.address for h in result.hops] == ["192.168.1.1", None, "100.64.0.1", "1.1.1.1"]
    assert result.raw.startswith("traceroute to 1.1.1.1")


@pytest.mark.asyncio
async def test_run_traceroute_reports_missing_binary(monkeypatch):
    async def fake_exec(*args, **kwargs):
        raise FileNotFoundError(args[0])

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    with pytest.raises(tr.TracerouteUnavailable, match="not installed"):
        await tr.run_traceroute("1.1.1.1")


@pytest.mark.asyncio
async def test_run_traceroute_returns_partial_hops_when_time_budget_runs_out(monkeypatch):
    procs: list[_FakeProc] = []

    async def fake_exec(*args, **kwargs):
        proc = _FakeProc(_FakeStream([b" 1  192.168.1.1  0.5 ms  0.5 ms  0.5 ms\n"], hang_after=True))
        procs.append(proc)
        return proc

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    result = await tr.run_traceroute("1.1.1.1", overall_timeout_seconds=0.05)
    assert result.timed_out is True
    assert procs[0].killed is True
    assert [h.address for h in result.hops] == ["192.168.1.1"]


@pytest.mark.asyncio
async def test_run_traceroute_rejects_unsafe_host_before_spawning(monkeypatch):
    async def fake_exec(*args, **kwargs):  # pragma: no cover - must not be reached
        raise AssertionError("subprocess must not be started for an unsafe host")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_exec)
    with pytest.raises(ValueError):
        await tr.run_traceroute("-oProxyCommand=x")
