from __future__ import annotations

import pytest

from app.monitoring import network_info

MACOS_HARDWARE_PORTS = """Hardware Port: Wi-Fi
Device: en0
Ethernet Address: aa:bb:cc:dd:ee:ff

Hardware Port: Bluetooth PAN
Device: en7
Ethernet Address: aa:bb:cc:dd:ee:00

"""

MACOS_ROUTE_WIFI = "   route to: default\ndestination: default\ninterface: en0\n"
MACOS_ROUTE_ETHERNET = "   route to: default\ndestination: default\ninterface: en5\n"
MACOS_SSID_CONNECTED = "Current Wi-Fi Network: HomeWiFi\n"
MACOS_SSID_DISCONNECTED = "You are not associated with an AirPort network.\n"


@pytest.fixture(autouse=True)
def _reset_cache():
    network_info.reset_cache()
    yield
    network_info.reset_cache()


def _fake_run(responses: dict[str, str]):
    async def fake(*args: str) -> str:
        return responses.get(args[0], "")
    return fake


@pytest.mark.asyncio
async def test_macos_returns_ssid_when_on_wifi(monkeypatch):
    monkeypatch.setattr(network_info, "_IS_MACOS", True)

    async def fake_run(*args: str) -> str:
        if args[0] == "networksetup" and args[1] == "-listallhardwareports":
            return MACOS_HARDWARE_PORTS
        if args[0] == "networksetup" and args[1] == "-getairportnetwork":
            return MACOS_SSID_CONNECTED
        if args[0] == "route":
            return MACOS_ROUTE_WIFI
        return ""

    monkeypatch.setattr(network_info, "_run", fake_run)
    name = await network_info.get_network_name(force=True)
    assert name == "HomeWiFi"


@pytest.mark.asyncio
async def test_macos_returns_wired_label_when_not_on_wifi(monkeypatch):
    monkeypatch.setattr(network_info, "_IS_MACOS", True)

    async def fake_run(*args: str) -> str:
        if args[0] == "networksetup" and args[1] == "-listallhardwareports":
            return MACOS_HARDWARE_PORTS
        if args[0] == "route":
            return MACOS_ROUTE_ETHERNET
        return ""

    monkeypatch.setattr(network_info, "_run", fake_run)
    name = await network_info.get_network_name(force=True)
    assert name == "Wired (en5)"


@pytest.mark.asyncio
async def test_macos_unknown_when_nothing_detected(monkeypatch):
    monkeypatch.setattr(network_info, "_IS_MACOS", True)
    monkeypatch.setattr(network_info, "_run", _fake_run({}))
    name = await network_info.get_network_name(force=True)
    assert name is None


@pytest.mark.asyncio
async def test_linux_uses_iwgetid_first(monkeypatch):
    monkeypatch.setattr(network_info, "_IS_MACOS", False)

    async def fake_run(*args: str) -> str:
        if args[0] == "iwgetid":
            return "OfficeWiFi\n"
        return ""

    monkeypatch.setattr(network_info, "_run", fake_run)
    name = await network_info.get_network_name(force=True)
    assert name == "OfficeWiFi"


@pytest.mark.asyncio
async def test_linux_falls_back_to_nmcli(monkeypatch):
    monkeypatch.setattr(network_info, "_IS_MACOS", False)

    async def fake_run(*args: str) -> str:
        if args[0] == "iwgetid":
            return ""
        if args[0] == "nmcli":
            return "no:SomeOtherNetwork\nyes:CoffeeShop\n"
        return ""

    monkeypatch.setattr(network_info, "_run", fake_run)
    name = await network_info.get_network_name(force=True)
    assert name == "CoffeeShop"


@pytest.mark.asyncio
async def test_linux_falls_back_to_wired_interface(monkeypatch):
    monkeypatch.setattr(network_info, "_IS_MACOS", False)

    async def fake_run(*args: str) -> str:
        if args[0] == "ip":
            return "default via 192.168.1.1 dev eth0 proto dhcp\n"
        return ""

    monkeypatch.setattr(network_info, "_run", fake_run)
    name = await network_info.get_network_name(force=True)
    assert name == "Wired (eth0)"


@pytest.mark.asyncio
async def test_result_is_cached_between_calls(monkeypatch):
    monkeypatch.setattr(network_info, "_IS_MACOS", False)
    call_count = 0

    async def fake_run(*args: str) -> str:
        nonlocal call_count
        call_count += 1
        return "CachedNet\n" if args[0] == "iwgetid" else ""

    monkeypatch.setattr(network_info, "_run", fake_run)
    first = await network_info.get_network_name()
    second = await network_info.get_network_name()
    assert first == second == "CachedNet"
    assert call_count == 1  # second call served from cache, no new subprocess


@pytest.mark.asyncio
async def test_never_raises_on_unexpected_error(monkeypatch):
    monkeypatch.setattr(network_info, "_IS_MACOS", False)

    async def boom(*args: str) -> str:
        raise RuntimeError("unexpected failure")

    monkeypatch.setattr(network_info, "_run", boom)
    name = await network_info.get_network_name(force=True)
    assert name is None
