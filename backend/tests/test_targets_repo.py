from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.database import targets_repo
from app.models.target import TargetCreate, TargetUpdate
from app.monitoring import network_info


@pytest.mark.asyncio
async def test_create_and_get_target(db):
    created = await targets_repo.create_target(db, TargetCreate(name="Router", host="192.168.1.1", protocol="icmp"))
    fetched = await targets_repo.get_target(db, created.id)
    assert fetched is not None
    assert fetched.name == "Router"
    assert fetched.host == "192.168.1.1"
    assert fetched.enabled is True


@pytest.mark.asyncio
async def test_list_targets_orders_gateway_first(db):
    await targets_repo.create_target(db, TargetCreate(name="DNS", host="8.8.8.8"))
    await targets_repo.create_target(db, TargetCreate(name="Gateway", host="192.168.1.1", is_gateway=True))
    targets = await targets_repo.list_targets(db)
    assert targets[0].is_gateway is True


@pytest.mark.asyncio
async def test_update_target_partial(db):
    created = await targets_repo.create_target(db, TargetCreate(name="DNS", host="8.8.8.8", interval_seconds=5))
    updated = await targets_repo.update_target(db, created.id, TargetUpdate(interval_seconds=30))
    assert updated is not None
    assert updated.interval_seconds == 30
    assert updated.host == "8.8.8.8"  # untouched


@pytest.mark.asyncio
async def test_update_missing_target_returns_none(db):
    result = await targets_repo.update_target(db, 9999, TargetUpdate(name="Nope"))
    assert result is None


@pytest.mark.asyncio
async def test_delete_target(db):
    created = await targets_repo.create_target(db, TargetCreate(name="DNS", host="8.8.8.8"))
    assert await targets_repo.delete_target(db, created.id) is True
    assert await targets_repo.get_target(db, created.id) is None
    assert await targets_repo.delete_target(db, created.id) is False


@pytest.mark.asyncio
async def test_detect_gateway_on_macos_uses_route_command(monkeypatch):
    monkeypatch.setattr(targets_repo.sys, "platform", "darwin")

    async def fake_gateway():
        return "10.119.5.254"

    monkeypatch.setattr(network_info, "get_default_gateway_macos", fake_gateway)
    gateway = await targets_repo._detect_gateway()
    assert gateway == "10.119.5.254"


@pytest.mark.asyncio
async def test_detect_gateway_on_macos_falls_back_when_undetectable(monkeypatch):
    monkeypatch.setattr(targets_repo.sys, "platform", "darwin")

    async def fake_gateway():
        return None

    monkeypatch.setattr(network_info, "get_default_gateway_macos", fake_gateway)
    gateway = await targets_repo._detect_gateway()
    assert gateway == "192.168.1.1"


@pytest.mark.asyncio
async def test_detect_gateway_on_macos_falls_back_on_error(monkeypatch):
    monkeypatch.setattr(targets_repo.sys, "platform", "darwin")

    async def fake_gateway():
        raise RuntimeError("route command not found")

    monkeypatch.setattr(network_info, "get_default_gateway_macos", fake_gateway)
    gateway = await targets_repo._detect_gateway()
    assert gateway == "192.168.1.1"


@pytest.mark.asyncio
async def test_detect_gateway_on_windows_uses_route_print(monkeypatch):
    monkeypatch.setattr(targets_repo.sys, "platform", "win32")

    async def fake_gateway():
        return "192.168.1.1"

    monkeypatch.setattr(network_info, "get_default_gateway_windows", fake_gateway)
    gateway = await targets_repo._detect_gateway()
    assert gateway == "192.168.1.1"


@pytest.mark.asyncio
async def test_detect_gateway_on_windows_falls_back_when_undetectable(monkeypatch):
    monkeypatch.setattr(targets_repo.sys, "platform", "win32")

    async def fake_gateway():
        return None

    monkeypatch.setattr(network_info, "get_default_gateway_windows", fake_gateway)
    gateway = await targets_repo._detect_gateway()
    assert gateway == "192.168.1.1"


@pytest.mark.asyncio
async def test_seed_default_targets_only_runs_once(db, monkeypatch):
    async def fake_wan_ip():
        return "203.0.113.1"
    monkeypatch.setattr(network_info, "get_wan_ip", fake_wan_ip)
    await targets_repo.seed_default_targets(db)
    first_count = len(await targets_repo.list_targets(db))
    assert first_count == 4

    await targets_repo.seed_default_targets(db)
    assert len(await targets_repo.list_targets(db)) == first_count


def test_rejects_invalid_hostname():
    with pytest.raises(ValidationError):
        TargetCreate(name="Bad", host="not a valid host!!", protocol="icmp")


def test_rejects_empty_name():
    with pytest.raises(ValidationError):
        TargetCreate(name="   ", host="1.1.1.1")


def test_rejects_out_of_range_port():
    with pytest.raises(ValidationError):
        TargetCreate(name="Web", host="example.com", protocol="tcp", port=70000)


def test_rejects_interval_below_minimum():
    with pytest.raises(ValidationError):
        TargetCreate(name="Fast", host="1.1.1.1", interval_seconds=0)


def test_accepts_valid_ip_and_hostname():
    a = TargetCreate(name="IP", host="10.0.0.1")
    b = TargetCreate(name="Hostname", host="cloudflare.com")
    assert a.host == "10.0.0.1"
    assert b.host == "cloudflare.com"


def test_tcp_target_defaults_port_to_443():
    t = TargetCreate(name="Web", host="example.com", protocol="tcp")
    assert t.port == 443
