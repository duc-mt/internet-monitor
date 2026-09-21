from __future__ import annotations

import asyncio

import pytest

from app.monitoring import pinger

SUCCESS_OUTPUT = """PING 1.1.1.1 (1.1.1.1) 56(84) bytes of data.
64 bytes from 1.1.1.1: icmp_seq=1 ttl=59 time=12.3 ms
64 bytes from 1.1.1.1: icmp_seq=2 ttl=59 time=11.9 ms
64 bytes from 1.1.1.1: icmp_seq=3 ttl=59 time=14.5 ms

--- 1.1.1.1 ping statistics ---
3 packets transmitted, 3 received, 0% packet loss, time 2003ms
rtt min/avg/max/mdev = 11.9/12.9/14.5/1.1 ms
"""

PARTIAL_LOSS_OUTPUT = """PING 8.8.8.8 (8.8.8.8) 56(84) bytes of data.
64 bytes from 8.8.8.8: icmp_seq=1 ttl=59 time=20.0 ms

--- 8.8.8.8 ping statistics ---
3 packets transmitted, 1 received, 66.6% packet loss, time 2010ms
"""

UNREACHABLE_OUTPUT = """PING 10.255.255.1 (10.255.255.1) 56(84) bytes of data.
From 192.168.1.1 icmp_seq=1 Destination Host Unreachable

--- 10.255.255.1 ping statistics ---
3 packets transmitted, 0 received, +3 errors, 100% packet loss, time 2000ms
"""

DNS_FAILURE_OUTPUT_ERR = "ping: badhostname.invalid: Name or service not known\n"

WINDOWS_SUCCESS_OUTPUT = """Pinging 8.8.8.8 with 32 bytes of data:
Reply from 8.8.8.8: bytes=32 time=15ms TTL=57
Reply from 8.8.8.8: bytes=32 time=14ms TTL=57
Reply from 8.8.8.8: bytes=32 time=16ms TTL=57

Ping statistics for 8.8.8.8:
    Packets: Sent = 3, Received = 3, Lost = 0 (0% loss),
Approximate round trip times in milli-seconds:
    Minimum = 14ms, Maximum = 16ms, Average = 15ms
"""

WINDOWS_TIMEOUT_OUTPUT = """Pinging 10.255.255.1 with 32 bytes of data:
Request timed out.
Request timed out.
Request timed out.

Ping statistics for 10.255.255.1:
    Packets: Sent = 3, Received = 0, Lost = 3 (100% loss),
"""

WINDOWS_UNREACHABLE_OUTPUT = """Pinging 10.0.0.99 with 32 bytes of data:
Reply from 10.0.0.5: Destination host unreachable.
Reply from 10.0.0.5: Destination host unreachable.
Reply from 10.0.0.5: Destination host unreachable.

Ping statistics for 10.0.0.99:
    Packets: Sent = 3, Received = 0, Lost = 3 (100% loss),
"""

WINDOWS_DNS_FAILURE_OUTPUT = (
    "Ping request could not find host badhostname.invalid. "
    "Please check the name and try again.\n"
)

WINDOWS_SUBMS_OUTPUT = """Pinging 1.1.1.1 with 32 bytes of data:
Reply from 1.1.1.1: bytes=32 time<1ms TTL=59
Reply from 1.1.1.1: bytes=32 time<1ms TTL=59

Ping statistics for 1.1.1.1:
    Packets: Sent = 2, Received = 2, Lost = 0 (0% loss),
"""


class FakeProcess:
    def __init__(self, stdout: bytes, stderr: bytes = b"", returncode: int = 0):
        self._stdout = stdout
        self._stderr = stderr
        self.returncode = returncode
        self.killed = False

    async def communicate(self):
        return self._stdout, self._stderr

    def kill(self):
        self.killed = True

    async def wait(self):
        return self.returncode


def test_compute_jitter_needs_two_samples():
    assert pinger.compute_jitter([]) is None
    assert pinger.compute_jitter([10.0]) is None


def test_compute_jitter_is_mean_abs_successive_diff():
    # |12-10| = 2, |9-12| = 3 -> mean = 2.5
    assert pinger.compute_jitter([10.0, 12.0, 9.0]) == 2.5


def test_ping_batch_result_loss_pct_all_success():
    result = pinger.PingBatchResult(method="icmp", attempted=3, succeeded=3, latencies=[10, 11, 12])
    assert result.loss_pct == 0.0
    assert result.success is True
    assert result.avg_latency_ms == 11.0


def test_ping_batch_result_loss_pct_total_failure():
    result = pinger.PingBatchResult(method="icmp", attempted=3, succeeded=0)
    assert result.loss_pct == 100.0
    assert result.success is False
    assert result.avg_latency_ms is None


@pytest.mark.asyncio
async def test_check_icmp_success(monkeypatch):
    monkeypatch.setattr(pinger, "icmp_available", lambda: True)

    async def fake_create_subprocess_exec(*args, **kwargs):
        return FakeProcess(SUCCESS_OUTPUT.encode())

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    result = await pinger.check_icmp("1.1.1.1", count=3, timeout=2.0)
    assert result.attempted == 3
    assert result.succeeded == 3
    assert result.latencies == [12.3, 11.9, 14.5]
    assert result.error is None
    assert result.loss_pct == 0.0


@pytest.mark.asyncio
async def test_check_icmp_partial_loss(monkeypatch):
    monkeypatch.setattr(pinger, "icmp_available", lambda: True)

    async def fake_create_subprocess_exec(*args, **kwargs):
        return FakeProcess(PARTIAL_LOSS_OUTPUT.encode())

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    result = await pinger.check_icmp("8.8.8.8", count=3, timeout=2.0)
    assert result.succeeded == 1
    assert result.attempted == 3
    assert abs(result.loss_pct - 66.67) < 0.5


@pytest.mark.asyncio
async def test_check_icmp_host_unreachable(monkeypatch):
    monkeypatch.setattr(pinger, "icmp_available", lambda: True)

    async def fake_create_subprocess_exec(*args, **kwargs):
        return FakeProcess(UNREACHABLE_OUTPUT.encode(), returncode=2)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    result = await pinger.check_icmp("10.255.255.1", count=3, timeout=2.0)
    assert result.succeeded == 0
    assert result.error == "host unreachable"


@pytest.mark.asyncio
async def test_check_icmp_dns_failure(monkeypatch):
    monkeypatch.setattr(pinger, "icmp_available", lambda: True)

    async def fake_create_subprocess_exec(*args, **kwargs):
        return FakeProcess(b"", DNS_FAILURE_OUTPUT_ERR.encode(), returncode=2)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    result = await pinger.check_icmp("badhostname.invalid", count=3, timeout=2.0)
    assert result.succeeded == 0
    assert result.error == "DNS resolution failed"


@pytest.mark.asyncio
async def test_check_icmp_windows_success(monkeypatch):
    monkeypatch.setattr(pinger, "icmp_available", lambda: True)
    monkeypatch.setattr(pinger, "_IS_WINDOWS", True)

    async def fake_create_subprocess_exec(*args, **kwargs):
        assert "-n" in args and "-w" in args
        assert "--" not in args  # Windows ping doesn't understand this
        return FakeProcess(WINDOWS_SUCCESS_OUTPUT.encode())

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    result = await pinger.check_icmp("8.8.8.8", count=3, timeout=2.0)
    assert result.attempted == 3
    assert result.succeeded == 3
    assert result.latencies == [15.0, 14.0, 16.0]
    assert result.error is None


@pytest.mark.asyncio
async def test_check_icmp_windows_handles_submillisecond_replies(monkeypatch):
    monkeypatch.setattr(pinger, "icmp_available", lambda: True)
    monkeypatch.setattr(pinger, "_IS_WINDOWS", True)

    async def fake_create_subprocess_exec(*args, **kwargs):
        return FakeProcess(WINDOWS_SUBMS_OUTPUT.encode())

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    result = await pinger.check_icmp("1.1.1.1", count=2, timeout=2.0)
    assert result.succeeded == 2
    assert result.latencies == [1.0, 1.0]  # "time<1ms" parsed via the shared regex


@pytest.mark.asyncio
async def test_check_icmp_windows_timeout(monkeypatch):
    monkeypatch.setattr(pinger, "icmp_available", lambda: True)
    monkeypatch.setattr(pinger, "_IS_WINDOWS", True)

    async def fake_create_subprocess_exec(*args, **kwargs):
        return FakeProcess(WINDOWS_TIMEOUT_OUTPUT.encode())

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    result = await pinger.check_icmp("10.255.255.1", count=3, timeout=2.0)
    assert result.succeeded == 0
    assert result.attempted == 3
    assert result.error == "request timed out"


@pytest.mark.asyncio
async def test_check_icmp_windows_host_unreachable(monkeypatch):
    monkeypatch.setattr(pinger, "icmp_available", lambda: True)
    monkeypatch.setattr(pinger, "_IS_WINDOWS", True)

    async def fake_create_subprocess_exec(*args, **kwargs):
        return FakeProcess(WINDOWS_UNREACHABLE_OUTPUT.encode())

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    result = await pinger.check_icmp("10.0.0.99", count=3, timeout=2.0)
    assert result.succeeded == 0
    assert result.error == "host unreachable"


@pytest.mark.asyncio
async def test_check_icmp_windows_dns_failure(monkeypatch):
    monkeypatch.setattr(pinger, "icmp_available", lambda: True)
    monkeypatch.setattr(pinger, "_IS_WINDOWS", True)

    async def fake_create_subprocess_exec(*args, **kwargs):
        return FakeProcess(WINDOWS_DNS_FAILURE_OUTPUT.encode())

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    result = await pinger.check_icmp("badhostname.invalid", count=3, timeout=2.0)
    assert result.succeeded == 0
    assert result.error == "DNS resolution failed"


@pytest.mark.asyncio
async def test_check_icmp_binary_missing_raises(monkeypatch):
    pinger._icmp_unavailable = None
    monkeypatch.setattr("shutil.which", lambda name: None)

    with pytest.raises(pinger.PingUnavailable):
        await pinger.check_icmp("1.1.1.1", count=3, timeout=2.0)
    pinger._icmp_unavailable = None


@pytest.mark.asyncio
async def test_check_icmp_times_out(monkeypatch):
    monkeypatch.setattr(pinger, "icmp_available", lambda: True)

    class HangingProcess(FakeProcess):
        async def communicate(self):
            await asyncio.sleep(10)
            return b"", b""

    async def fake_create_subprocess_exec(*args, **kwargs):
        return HangingProcess(b"")

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    result = await pinger.check_icmp("1.1.1.1", count=1, timeout=0.05)
    assert result.succeeded == 0
    assert result.error == "ping timed out"


async def _close_immediately(reader, writer):
    writer.close()
    try:
        await writer.wait_closed()
    except OSError:
        pass


@pytest.mark.asyncio
async def test_check_tcp_against_local_server():
    server = await asyncio.start_server(_close_immediately, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    try:
        result = await pinger.check_tcp("127.0.0.1", port, count=3, timeout=1.0)
        assert result.method == "tcp"
        assert result.succeeded == 3
        assert result.loss_pct == 0.0
        assert all(l >= 0 for l in result.latencies)
    finally:
        server.close()
        await server.wait_closed()


@pytest.mark.asyncio
async def test_check_tcp_connection_refused():
    # Nothing is listening on this port - connection should be refused fast.
    server = await asyncio.start_server(lambda r, w: None, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    server.close()
    await server.wait_closed()

    result = await pinger.check_tcp("127.0.0.1", port, count=2, timeout=1.0)
    assert result.succeeded == 0
    assert result.error == "connection refused"


@pytest.mark.asyncio
async def test_run_check_falls_back_to_tcp_when_icmp_unavailable(monkeypatch):
    pinger._icmp_unavailable = None
    monkeypatch.setattr("shutil.which", lambda name: None)

    server = await asyncio.start_server(_close_immediately, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    try:
        result = await pinger.run_check(host="127.0.0.1", protocol="icmp", port=port, count=2, timeout=1.0)
        assert result.method == "tcp"
        assert result.succeeded == 2
        assert result.error is None  # successful fallback shouldn't be flagged as an error
    finally:
        server.close()
        await server.wait_closed()
        pinger._icmp_unavailable = None
