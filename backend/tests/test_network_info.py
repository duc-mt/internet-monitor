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

# Trimmed but structurally faithful to real `system_profiler SPAirPortDataType`
# output (macOS 15/Sequoia, where networksetup's SSID lookup is blocked) -
# note the awdl0 (AirDrop) block also has a "Current Network Information:"
# section, but with no name header, straight to "Network Type: Infrastructure".
MACOS_SYSTEM_PROFILER_OUTPUT = """Wi-Fi:

      Interfaces:
        en0:
          Card Type: Wi-Fi
          Status: Connected
          Current Network Information:
            HomeNetworkVN:
              PHY Mode: 802.11ac
              Channel: 100 (5GHz, 40MHz)
              Security: WPA2 Personal
          Other Local Wi-Fi Networks:
            SomeNeighborWiFi:
              PHY Mode: 802.11a/n/ac/ax
              Security: WPA2 Personal
        awdl0:
          MAC Address: 7a:c8:7d:64:90:2a
          Current Network Information:
              Network Type: Infrastructure
"""


@pytest.fixture(autouse=True)
def _reset_cache():
    network_info.reset_cache()
    yield
    network_info.reset_cache()


def _fake_run(responses: dict[str, str]):
    async def fake(*args: str, timeout: float = 3.0) -> str:
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
async def test_macos_falls_back_to_system_profiler_when_networksetup_is_blocked(monkeypatch):
    """networksetup -getairportnetwork returns no usable SSID on macOS 15+
    (a deliberate OS restriction) - system_profiler must be tried next."""
    monkeypatch.setattr(network_info, "_IS_MACOS", True)

    async def fake_run(*args: str, timeout: float = 3.0) -> str:
        if args[0] == "networksetup" and args[1] == "-listallhardwareports":
            return MACOS_HARDWARE_PORTS
        if args[0] == "networksetup" and args[1] == "-getairportnetwork":
            return MACOS_SSID_DISCONNECTED  # what macOS 15 actually returns now
        if args[0] == "system_profiler":
            return MACOS_SYSTEM_PROFILER_OUTPUT
        if args[0] == "route":
            return MACOS_ROUTE_WIFI
        return ""

    monkeypatch.setattr(network_info, "_run", fake_run)
    name = await network_info.get_network_name(force=True)
    assert name == "HomeNetworkVN"


@pytest.mark.asyncio
async def test_system_profiler_parser_ignores_awdl_block(monkeypatch):
    monkeypatch.setattr(network_info, "_IS_MACOS", True)

    async def fake_run(*args: str, timeout: float = 3.0) -> str:
        return MACOS_SYSTEM_PROFILER_OUTPUT if args[0] == "system_profiler" else ""

    monkeypatch.setattr(network_info, "_run", fake_run)
    ssid = await network_info._macos_ssid_via_system_profiler()
    assert ssid == "HomeNetworkVN"
    assert ssid != "Network Type"  # the awdl0 block must never be picked up


@pytest.mark.asyncio
async def test_system_profiler_parser_returns_none_when_no_match(monkeypatch):
    monkeypatch.setattr(network_info, "_run", _fake_run({}))
    assert await network_info._macos_ssid_via_system_profiler() is None


@pytest.mark.asyncio
async def test_macos_does_not_call_system_profiler_when_networksetup_succeeds(monkeypatch):
    """The slow fallback must only run when the fast path actually fails."""
    monkeypatch.setattr(network_info, "_IS_MACOS", True)
    system_profiler_called = False

    async def fake_run(*args: str, timeout: float = 3.0) -> str:
        nonlocal system_profiler_called
        if args[0] == "networksetup" and args[1] == "-listallhardwareports":
            return MACOS_HARDWARE_PORTS
        if args[0] == "networksetup" and args[1] == "-getairportnetwork":
            return MACOS_SSID_CONNECTED
        if args[0] == "system_profiler":
            system_profiler_called = True
            return MACOS_SYSTEM_PROFILER_OUTPUT
        if args[0] == "route":
            return MACOS_ROUTE_WIFI
        return ""

    monkeypatch.setattr(network_info, "_run", fake_run)
    name = await network_info.get_network_name(force=True)
    assert name == "HomeWiFi"
    assert system_profiler_called is False


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
async def test_macos_default_gateway_parses_route_output(monkeypatch):
    async def fake_run(*args: str) -> str:
        if args[0] == "route":
            return "   route to: default\ndestination: default\nmask: default\ngateway: 10.119.5.254\ninterface: en0\n"
        return ""

    monkeypatch.setattr(network_info, "_run", fake_run)
    gateway = await network_info.get_default_gateway_macos()
    assert gateway == "10.119.5.254"


@pytest.mark.asyncio
async def test_macos_default_gateway_none_when_unparseable(monkeypatch):
    monkeypatch.setattr(network_info, "_run", _fake_run({}))
    gateway = await network_info.get_default_gateway_macos()
    assert gateway is None


WINDOWS_ROUTE_PRINT_OUTPUT = """===========================================================================
Interface List
 12...00 15 5d 01 ab 02 ......Microsoft Hyper-V Network Adapter
  1...........................Software Loopback Interface 1
===========================================================================

IPv4 Route Table
===========================================================================
Active Routes:
Network Destination        Netmask          Gateway       Interface  Metric
          0.0.0.0          0.0.0.0    192.168.1.1    192.168.1.100     25
        127.0.0.0        255.0.0.0         On-link         127.0.0.1    331
===========================================================================
"""

WINDOWS_WLAN_CONNECTED_OUTPUT = """There is 1 interface on the system:

    Name                   : Wi-Fi
    Description            : Intel(R) Wi-Fi 6 AX201 160MHz
    GUID                   : xxxx-xxxx-xxxx-xxxx
    Physical address       : xx:xx:xx:xx:xx:xx
    State                  : connected
    SSID                   : OfficeWiFi
    BSSID                  : xx:xx:xx:xx:xx:xx
    Network type           : Infrastructure
    Radio type             : 802.11ac
    Channel                : 44
    Signal                 : 80%
    Profile                : OfficeWiFi
"""

WINDOWS_WLAN_DISCONNECTED_OUTPUT = """There is 1 interface on the system:

    Name                   : Wi-Fi
    Description            : Intel(R) Wi-Fi 6 AX201 160MHz
    GUID                   : xxxx-xxxx-xxxx-xxxx
    Physical address       : xx:xx:xx:xx:xx:xx
    State                  : disconnected
"""


@pytest.mark.asyncio
async def test_windows_default_gateway_parses_route_print(monkeypatch):
    monkeypatch.setattr(network_info, "_run", _fake_run({"route": WINDOWS_ROUTE_PRINT_OUTPUT}))
    gateway = await network_info.get_default_gateway_windows()
    assert gateway == "192.168.1.1"


@pytest.mark.asyncio
async def test_windows_default_gateway_none_when_unparseable(monkeypatch):
    monkeypatch.setattr(network_info, "_run", _fake_run({}))
    assert await network_info.get_default_gateway_windows() is None


@pytest.mark.asyncio
async def test_windows_network_name_returns_ssid_when_connected(monkeypatch):
    monkeypatch.setattr(network_info, "_IS_WINDOWS", True)
    monkeypatch.setattr(network_info, "_IS_MACOS", False)
    monkeypatch.setattr(network_info, "_run", _fake_run({"netsh": WINDOWS_WLAN_CONNECTED_OUTPUT}))
    name = await network_info.get_network_name(force=True)
    assert name == "OfficeWiFi"


@pytest.mark.asyncio
async def test_windows_network_name_does_not_match_bssid(monkeypatch):
    # BSSID must never be mistaken for SSID - the regex is anchored to
    # line-start, so "    BSSID   : ..." can never match "^\s*SSID".
    ssid = network_info._WINDOWS_SSID_RE.search(WINDOWS_WLAN_CONNECTED_OUTPUT)
    assert ssid.group(1) == "OfficeWiFi"


@pytest.mark.asyncio
async def test_windows_network_name_falls_back_to_wired_when_disconnected(monkeypatch):
    monkeypatch.setattr(network_info, "_IS_WINDOWS", True)
    monkeypatch.setattr(network_info, "_IS_MACOS", False)

    async def fake_run(*args: str, timeout: float = 3.0) -> str:
        if args[0] == "netsh":
            return WINDOWS_WLAN_DISCONNECTED_OUTPUT
        if args[0] == "route":
            return WINDOWS_ROUTE_PRINT_OUTPUT
        return ""

    monkeypatch.setattr(network_info, "_run", fake_run)
    name = await network_info.get_network_name(force=True)
    assert name == "Wired"


@pytest.mark.asyncio
async def test_windows_network_name_none_when_nothing_detected(monkeypatch):
    monkeypatch.setattr(network_info, "_IS_WINDOWS", True)
    monkeypatch.setattr(network_info, "_IS_MACOS", False)
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
