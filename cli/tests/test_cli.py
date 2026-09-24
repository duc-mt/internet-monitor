from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner
from internet_monitor_cli.main import (
    ApiClient,
    _dotted_get,
    _dotted_set,
    _fmt_ms,
    _fmt_pct,
    _parse_scalar,
    cli,
)


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def mock_client():
    client = MagicMock(spec=ApiClient)
    client.base_url = "http://127.0.0.1:8765/api"
    return client


def test_helpers():
    assert _fmt_ms(None) == "—"
    assert _fmt_ms(12.345) == "12.3 ms"
    assert _fmt_pct(None) == "—"
    assert _fmt_pct(5.0) == "5.0%"

    assert _parse_scalar("true") is True
    assert _parse_scalar("FALSE") is False
    assert _parse_scalar("123") == 123
    assert _parse_scalar("45.67") == 45.67
    assert _parse_scalar("hello") == "hello"

    data = {"a": {"b": {"c": 42}}}
    assert _dotted_get(data, "a.b.c") == 42
    with pytest.raises(Exception):
        _dotted_get(data, "a.b.missing")

    updated = _dotted_set({}, "x.y.z", "value")
    assert updated == {"x": {"y": {"z": "value"}}}


def test_status_text(runner, mock_client):
    mock_client.get.return_value = {
        "online": True,
        "quality": "good",
        "latency_ms": 15.2,
        "packet_loss": 0.0,
        "jitter_ms": 2.1,
        "targets_reachable": 4,
        "targets_total": 4,
        "monitoring_running": True,
        "monitoring_uptime_seconds": 3600,
        "active_outage": False,
    }
    with patch("internet_monitor_cli.main.ApiClient", return_value=mock_client):
        result = runner.invoke(cli, ["status"])
        assert result.exit_code == 0
        assert "ONLINE" in result.output
        assert "15.2 ms" in result.output
        assert "4/4" in result.output


def test_status_json(runner, mock_client):
    payload = {
        "online": False,
        "quality": "offline",
        "latency_ms": None,
        "packet_loss": 100.0,
        "jitter_ms": None,
        "targets_reachable": 0,
        "targets_total": 3,
        "monitoring_running": True,
        "monitoring_uptime_seconds": 120,
        "active_outage": True,
    }
    mock_client.get.return_value = payload
    with patch("internet_monitor_cli.main.ApiClient", return_value=mock_client):
        result = runner.invoke(cli, ["status", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["online"] is False
        assert data["active_outage"] is True


def test_monitoring_start_stop(runner, mock_client):
    mock_client.post.side_effect = [{"running": True}, {"running": False}]
    with patch("internet_monitor_cli.main.ApiClient", return_value=mock_client):
        res_start = runner.invoke(cli, ["start"])
        assert res_start.exit_code == 0
        assert "Monitoring started." in res_start.output

        res_stop = runner.invoke(cli, ["stop"])
        assert res_stop.exit_code == 0
        assert "Monitoring stopped." in res_stop.output


def test_targets_crud(runner, mock_client):
    mock_client.get.return_value = [
        {
            "id": 1,
            "name": "Cloudflare DNS",
            "host": "1.1.1.1",
            "protocol": "icmp",
            "interval_seconds": 5,
            "enabled": True,
            "is_gateway": False,
        }
    ]
    mock_client.post.return_value = {"id": 2, "name": "Google DNS"}
    mock_client.put.return_value = {"id": 1, "name": "Updated DNS"}
    mock_client.delete.return_value = None

    with patch("internet_monitor_cli.main.ApiClient", return_value=mock_client):
        res_list = runner.invoke(cli, ["targets", "list"])
        assert res_list.exit_code == 0
        assert "Cloudflare DNS" in res_list.output

        res_add = runner.invoke(cli, ["targets", "add", "Google DNS", "8.8.8.8", "--interval", "10"])
        assert res_add.exit_code == 0
        assert "Created target #2" in res_add.output

        res_edit = runner.invoke(cli, ["targets", "edit", "1", "--name", "Updated DNS"])
        assert res_edit.exit_code == 0
        assert "Updated target #1" in res_edit.output

        res_del = runner.invoke(cli, ["targets", "remove", "1", "--yes"])
        assert res_del.exit_code == 0
        assert "Deleted target #1." in res_del.output


def test_history(runner, mock_client):
    mock_client.get.side_effect = [
        {
            "avg_latency_ms": 12.0,
            "min_latency_ms": 10.0,
            "max_latency_ms": 20.0,
            "p95_latency_ms": 18.0,
            "packet_loss_pct": 0.0,
            "avg_jitter_ms": 1.5,
            "outage_count": 0,
            "sample_count": 50,
        },
        [
            {
                "timestamp": "2026-09-24T00:00:00Z",
                "target_name": "Cloudflare",
                "target_id": 1,
                "latency_ms": 11.2,
                "packet_loss": 0.0,
                "success": True,
            }
        ],
    ]
    with patch("internet_monitor_cli.main.ApiClient", return_value=mock_client):
        result = runner.invoke(cli, ["history"])
        assert result.exit_code == 0
        assert "Statistics (24h):" in result.output
        assert "Cloudflare" in result.output


def test_config(runner, mock_client):
    mock_client.get.return_value = {"notifications": {"on_offline": True, "cooldown_seconds": 60}}
    mock_client.put.return_value = {"notifications": {"on_offline": False, "cooldown_seconds": 60}}

    with patch("internet_monitor_cli.main.ApiClient", return_value=mock_client):
        res_get_all = runner.invoke(cli, ["config", "get"])
        assert res_get_all.exit_code == 0
        assert "notifications" in res_get_all.output

        res_get_one = runner.invoke(cli, ["config", "get", "notifications.on_offline"])
        assert res_get_one.exit_code == 0
        assert "true" in res_get_one.output.lower()

        res_set = runner.invoke(cli, ["config", "set", "notifications.on_offline", "false"])
        assert res_set.exit_code == 0
        assert "notifications.on_offline = False" in res_set.output
