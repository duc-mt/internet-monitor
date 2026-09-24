from __future__ import annotations

import asyncio
import time

import pytest
from app.services import speedtest_service


class _FakeResponse:
    def __init__(self, chunks: list[bytes]):
        self._chunks = chunks

    def raise_for_status(self) -> None:
        pass

    def iter_content(self, chunk_size: int):
        yield from self._chunks

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_blocking_download_computes_mbps(monkeypatch):
    chunks = [b"x" * 1_000_000 for _ in range(5)]  # 5,000,000 bytes total

    def fake_get(url, params, stream, timeout):
        assert url == speedtest_service._TEST_URL
        assert params == {"bytes": 5_000_000}
        return _FakeResponse(chunks)

    monkeypatch.setattr(speedtest_service.requests, "get", fake_get)

    # Deterministic 1.0-second "elapsed" so the Mbps math is exact:
    # 5,000,000 bytes * 8 bits / 1,000,000 / 1.0s = 40.0 Mbps.
    clock = iter([0.0, 1.0])
    monkeypatch.setattr(speedtest_service.time, "monotonic", lambda: next(clock))

    result = speedtest_service._blocking_download(5_000_000, timeout=15.0)
    assert result.bytes_downloaded == 5_000_000
    assert result.download_mbps == 40.0
    assert result.elapsed_seconds == 1.0
    assert result.server == "speed.cloudflare.com"


def test_blocking_download_propagates_http_errors(monkeypatch):
    class _FailingResponse(_FakeResponse):
        def raise_for_status(self):
            raise speedtest_service.requests.HTTPError("503 Server Error")

    def fake_get(url, params, stream, timeout):
        return _FailingResponse([])

    monkeypatch.setattr(speedtest_service.requests, "get", fake_get)
    with pytest.raises(speedtest_service.requests.HTTPError):
        speedtest_service._blocking_download(1000, timeout=15.0)


@pytest.mark.asyncio
async def test_run_speedtest_does_not_block_the_event_loop(monkeypatch):
    """
    The whole point of using asyncio.to_thread is that a slow (blocking)
    download must not stall other coroutines - like the ping scheduler -
    running on the same event loop. This proves it concretely: a ticker
    task keeps incrementing a counter via asyncio.sleep() *while* a
    genuinely blocking time.sleep() stands in for the download.
    """

    def fake_blocking_download(size_bytes, timeout):
        time.sleep(0.3)  # real, OS-level blocking sleep - not asyncio.sleep
        return speedtest_service.SpeedtestResult(
            download_mbps=42.0,
            bytes_downloaded=size_bytes,
            elapsed_seconds=0.3,
            server="test",
        )

    monkeypatch.setattr(speedtest_service, "_blocking_download", fake_blocking_download)

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
    # If run_speedtest had blocked the loop, the ticker could not have run
    # at all during the ~0.3s "download" - it would be 0 or 1.
    assert tick_count >= 5
