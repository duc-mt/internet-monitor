"""
==============================================================================
Module Name:   test_speedtest_service.py
Description:   Source module test_speedtest_service.py.
Author:        Mai Tan Duc <ducmai.network@gmail.com>
Created:       2026-10-10
Version:       1.0.0
License:       MIT
==============================================================================
Usage:         python3 test_speedtest_service.py [options]
Notes:         Requires Python 3.8+
==============================================================================
"""

from __future__ import annotations

import asyncio
import types

import httpx
import pytest
from app.services import speedtest_service


def _transport(handler) -> httpx.MockTransport:
    return httpx.MockTransport(handler)


async def test_download_computes_mbps_and_streams_the_payload(monkeypatch):
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url.copy_with(query=None))
        seen["bytes"] = request.url.params["bytes"]
        return httpx.Response(200, content=b"x" * 5_000_000)

    # Deterministic 1.0-second "elapsed" so the Mbps math is exact:
    # 5,000,000 bytes * 8 bits / 1,000,000 / 1.0s = 40.0 Mbps.
    # (Patch the module's own `time` reference - patching time.monotonic itself
    # would also hijack the asyncio event loop's clock.)
    clock = iter([0.0, 1.0])
    monkeypatch.setattr(speedtest_service, "time", types.SimpleNamespace(monotonic=lambda: next(clock)))

    result = await speedtest_service._download(5_000_000, timeout=15.0, transport=_transport(handler))

    assert seen == {"url": speedtest_service._TEST_URL, "bytes": "5000000"}
    assert result.bytes_downloaded == 5_000_000
    assert result.download_mbps == 40.0
    assert result.elapsed_seconds == 1.0
    assert result.server == "speed.cloudflare.com"


async def test_download_propagates_http_errors():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    with pytest.raises(httpx.HTTPStatusError):
        await speedtest_service._download(1000, timeout=15.0, transport=_transport(handler))


async def test_download_propagates_timeouts():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow server", request=request)

    with pytest.raises(httpx.ReadTimeout):
        await speedtest_service._download(1000, timeout=0.1, transport=_transport(handler))


async def test_run_speedtest_does_not_block_the_event_loop(monkeypatch):
    """
    A slow download must not stall other coroutines - like the ping
    scheduler - on the same event loop. A ticker task keeps incrementing a
    counter while the (async-sleeping) "download" is in flight.
    """

    async def fake_download(size_bytes, timeout, *, transport=None):
        await asyncio.sleep(0.3)
        return speedtest_service.SpeedtestResult(
            download_mbps=42.0, bytes_downloaded=size_bytes, elapsed_seconds=0.3, server="test"
        )

    monkeypatch.setattr(speedtest_service, "_download", fake_download)

    tick_count = 0

    async def ticker():
        nonlocal tick_count
        while True:
            tick_count += 1
            await asyncio.sleep(0.02)

    ticker_task = asyncio.create_task(ticker())
    result = await speedtest_service.run_speedtest()
    ticker_task.cancel()

    assert result.download_mbps == 42.0
    assert tick_count >= 5


def test_requests_is_no_longer_a_dependency():
    import pathlib

    reqs = (pathlib.Path(__file__).resolve().parents[1] / "requirements.txt").read_text().lower()
    assert "requests" not in reqs
    assert not hasattr(speedtest_service, "requests")
