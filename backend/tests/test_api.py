from __future__ import annotations

"""
==============================================================================
Module Name:   test_api.py
Description:   Implementation and logic for test_api.
Author:        Mai Tan Duc <ducmai.network@gmail.com>
Created:       2026-10-10
Version:       1.0.0
License:       MIT
==============================================================================
Usage:         python3 test_api.py [options]
Notes:         Requires Python 3.8+
==============================================================================
"""


def test_health(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_default_targets_seeded_on_startup(client):
    resp = client.get("/api/targets")
    assert resp.status_code == 200
    names = {t["name"] for t in resp.json()}
    assert {"Gateway", "Cloudflare DNS", "Google DNS"} <= names


def test_create_list_update_delete_target(client):
    create_resp = client.post(
        "/api/targets",
        json={
            "name": "Custom Host",
            "host": "example.com",
            "protocol": "tcp",
            "port": 443,
            "interval_seconds": 10,
        },
    )
    assert create_resp.status_code == 201
    target = create_resp.json()
    assert target["name"] == "Custom Host"

    get_resp = client.get(f"/api/targets/{target['id']}")
    assert get_resp.status_code == 200

    update_resp = client.put(f"/api/targets/{target['id']}", json={"interval_seconds": 20})
    assert update_resp.status_code == 200
    assert update_resp.json()["interval_seconds"] == 20

    delete_resp = client.delete(f"/api/targets/{target['id']}")
    assert delete_resp.status_code == 204

    missing_resp = client.get(f"/api/targets/{target['id']}")
    assert missing_resp.status_code == 404


def test_create_target_rejects_invalid_host(client):
    resp = client.post("/api/targets", json={"name": "Bad", "host": "not a host!!", "protocol": "icmp"})
    assert resp.status_code == 422


def test_create_target_rejects_bad_interval(client):
    resp = client.post("/api/targets", json={"name": "Fast", "host": "1.1.1.1", "interval_seconds": 0})
    assert resp.status_code == 422


def test_update_nonexistent_target_404s(client):
    resp = client.put("/api/targets/99999", json={"name": "Ghost"})
    assert resp.status_code == 404


def test_delete_nonexistent_target_404s(client):
    resp = client.delete("/api/targets/99999")
    assert resp.status_code == 404


def test_status_endpoint_shape(client):
    resp = client.get("/api/status")
    assert resp.status_code == 200
    body = resp.json()
    for key in (
        "online",
        "quality",
        "targets_reachable",
        "targets_total",
        "targets",
        "monitoring_running",
        "network_name",
        "uptime_pct_24h",
    ):
        assert key in body


def test_settings_get_and_partial_update(client):
    get_resp = client.get("/api/settings")
    assert get_resp.status_code == 200
    original = get_resp.json()
    assert original["data_retention_days"] == 30

    put_resp = client.put("/api/settings", json={"data_retention_days": 90})
    assert put_resp.status_code == 200
    updated = put_resp.json()
    assert updated["data_retention_days"] == 90
    # untouched fields survive a partial update
    assert updated["theme"] == original["theme"]


def test_settings_update_nested_notifications(client):
    resp = client.put("/api/settings", json={"notifications": {"on_offline": False}})
    assert resp.status_code == 200
    assert resp.json()["notifications"]["on_offline"] is False
    # sibling notification fields keep their defaults
    assert resp.json()["notifications"]["on_online"] is True


def test_settings_sla_target_defaults_and_round_trips(client):
    assert client.get("/api/settings").json()["sla_target_pct"] == 99.9

    resp = client.put("/api/settings", json={"sla_target_pct": 99.5})
    assert resp.status_code == 200
    assert resp.json()["sla_target_pct"] == 99.5
    # persisted, not just echoed back
    assert client.get("/api/settings").json()["sla_target_pct"] == 99.5


def test_settings_sla_target_rejects_out_of_range_values(client):
    for bad in (0, -1, 100.1, 250):
        assert client.put("/api/settings", json={"sla_target_pct": bad}).status_code == 422
    assert client.get("/api/settings").json()["sla_target_pct"] == 99.9


def test_statistics_exposes_downtime_and_monitored_seconds(client):
    body = client.get("/api/statistics").json()
    assert body["downtime_seconds"] == 0.0
    assert body["effective_monitored_seconds"] == 0.0


def test_settings_webhook_url_defaults_to_none_and_is_masked_once_set(client):
    assert client.get("/api/settings").json()["notifications"]["webhook_url"] is None

    url = "https://hooks.slack.com/services/T000/B000/secret-token"
    resp = client.put("/api/settings", json={"notifications": {"webhook_url": url}})
    assert resp.status_code == 200
    masked = resp.json()["notifications"]["webhook_url"]
    # Scheme and host are kept (so you can tell "yes, this is Slack"), the
    # token-bearing path is not - the API never echoes the real URL back.
    assert masked == "https://hooks.slack.com/\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022"
    assert "secret-token" not in masked
    # sibling notification fields keep their values
    assert resp.json()["notifications"]["on_offline"] is True
    assert client.get("/api/settings").json()["notifications"]["webhook_url"] == masked


def test_settings_webhook_url_survives_an_unrelated_save_with_the_mask_echoed_back(client):
    """
    Mirrors what the Settings page actually does: it loads the (masked) GET
    response into its form state and PUTs the whole form back on every save,
    including fields the user didn't touch.
    """
    from app.services import settings_service

    url = "https://hooks.slack.com/services/T000/B000/secret-token"
    client.put("/api/settings", json={"notifications": {"webhook_url": url}})
    masked = client.get("/api/settings").json()["notifications"]["webhook_url"]

    resp = client.put("/api/settings", json={"notifications": {"webhook_url": masked, "cooldown_seconds": 120}})
    assert resp.status_code == 200
    assert resp.json()["notifications"]["cooldown_seconds"] == 120
    assert resp.json()["notifications"]["webhook_url"] == masked

    # The real secret underneath was preserved, not overwritten with the mask text.
    assert settings_service._cached.notifications.webhook_url == url


def test_settings_webhook_url_can_be_changed_to_a_different_real_url(client):
    from app.services import settings_service

    client.put("/api/settings", json={"notifications": {"webhook_url": "https://hooks.slack.com/a/b/old-token"}})
    new_url = "https://discord.com/api/webhooks/123456/new-token"
    resp = client.put("/api/settings", json={"notifications": {"webhook_url": new_url}})
    assert resp.status_code == 200
    assert (
        resp.json()["notifications"]["webhook_url"]
        == "https://discord.com/\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022"
    )
    assert settings_service._cached.notifications.webhook_url == new_url


def test_settings_webhook_url_can_be_cleared_with_an_empty_string(client):
    url = "https://alerts.example.net/hook"
    client.put("/api/settings", json={"notifications": {"webhook_url": url}})
    # The settings form sends "" (or null) when the field is emptied.
    resp = client.put("/api/settings", json={"notifications": {"webhook_url": ""}})
    assert resp.status_code == 200
    assert resp.json()["notifications"]["webhook_url"] is None


def test_settings_webhook_url_rejects_non_http_urls(client):
    for bad in ("ftp://example.net/hook", "javascript:alert(1)", "not a url", "https://"):
        resp = client.put("/api/settings", json={"notifications": {"webhook_url": bad}})
        assert resp.status_code == 422, bad
    assert client.get("/api/settings").json()["notifications"]["webhook_url"] is None


def test_statistics_requires_bounds_for_custom_range(client):
    resp = client.get("/api/statistics", params={"range": "custom"})
    assert resp.status_code == 400


def test_statistics_default_range(client):
    resp = client.get("/api/statistics")
    assert resp.status_code == 200
    body = resp.json()
    assert body["sample_count"] == 0


def test_outages_list_empty_initially(client):
    resp = client.get("/api/outages")
    assert resp.status_code == 200
    assert resp.json() == []


def test_monitoring_start_and_stop(client):
    start_resp = client.post("/api/monitoring/start")
    assert start_resp.status_code == 200
    assert start_resp.json()["running"] is True

    stop_resp = client.post("/api/monitoring/stop")
    assert stop_resp.status_code == 200
    assert stop_resp.json()["running"] is False


def test_export_measurements_csv(client):
    resp = client.get("/api/export/measurements.csv")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    assert "timestamp" in resp.text.splitlines()[0]


def test_speedtest_endpoint(client, monkeypatch):
    from app.services.speedtest_service import SpeedtestResult

    async def fake_run_speedtest(size_bytes=None):
        return SpeedtestResult(download_mbps=87.5, bytes_downloaded=10_000_000, elapsed_seconds=0.9, server="test")

    import app.api.speedtest as speedtest_module

    monkeypatch.setattr(speedtest_module, "run_speedtest", fake_run_speedtest)

    resp = client.post("/api/speedtest")
    assert resp.status_code == 200
    body = resp.json()
    assert body["download_mbps"] == 87.5
    assert body["server"] == "test"


def test_speedtest_endpoint_surfaces_failure_as_502(client, monkeypatch):
    async def fake_run_speedtest(size_bytes=None):
        raise RuntimeError("connection reset")

    import app.api.speedtest as speedtest_module

    monkeypatch.setattr(speedtest_module, "run_speedtest", fake_run_speedtest)

    resp = client.post("/api/speedtest")
    assert resp.status_code == 502


def test_export_report_json(client):
    resp = client.get("/api/export/report.json")
    assert resp.status_code == 200
    body = resp.json()
    assert "statistics" in body and "outages" in body


def test_speedtest_endpoint_rejects_concurrent_runs_with_409(client, monkeypatch):
    import app.api.speedtest as speedtest_module

    # Mock lock being already held
    monkeypatch.setattr(speedtest_module._speedtest_lock, "locked", lambda: True)

    resp = client.post("/api/speedtest")
    assert resp.status_code == 409
    assert "already in progress" in resp.json()["detail"]


def test_traceroute_unknown_target_404s(client):
    assert client.post("/api/targets/99999/traceroute").status_code == 404


def test_traceroute_returns_parsed_hops(client, monkeypatch):
    from app.monitoring import traceroute

    target = client.get("/api/targets").json()[0]

    async def fake_run(host, **kwargs):
        return traceroute.TracerouteResult(
            host=host,
            raw=" 1  192.168.1.1  1.0 ms  2.0 ms  *",
            hops=[traceroute.Hop(hop=1, address="192.168.1.1", rtts_ms=[1.0, 2.0, None], scope="private")],
        )

    monkeypatch.setattr(traceroute, "run_traceroute", fake_run)
    resp = client.post(f"/api/targets/{target['id']}/traceroute")
    assert resp.status_code == 200
    body = resp.json()
    assert body["target_id"] == target["id"]
    assert body["host"] == target["host"]
    assert body["timed_out"] is False
    assert body["hops"] == [
        {
            "hop": 1,
            "address": "192.168.1.1",
            "rtts_ms": [1.0, 2.0, None],
            "avg_ms": 1.5,
            "loss_pct": 33.3,
            "scope": "private",
            "extra_addresses": [],
        }
    ]
    assert "192.168.1.1" in body["raw"]


def test_traceroute_503_when_binary_missing(client, monkeypatch):
    from app.monitoring import traceroute

    target = client.get("/api/targets").json()[0]

    async def fake_run(host, **kwargs):
        raise traceroute.TracerouteUnavailable("traceroute is not installed on this system")

    monkeypatch.setattr(traceroute, "run_traceroute", fake_run)
    resp = client.post(f"/api/targets/{target['id']}/traceroute")
    assert resp.status_code == 503
    assert "not installed" in resp.json()["detail"]


def test_traceroute_409_when_already_running_for_that_target(client):
    import app.api.targets as targets_module

    target = client.get("/api/targets").json()[0]
    targets_module._traces_in_flight.add(target["id"])
    try:
        resp = client.post(f"/api/targets/{target['id']}/traceroute")
    finally:
        targets_module._traces_in_flight.discard(target["id"])
    assert resp.status_code == 409
    assert "already in progress" in resp.json()["detail"]


def test_traceroute_releases_the_in_flight_slot_after_a_failure(client, monkeypatch):
    import app.api.targets as targets_module
    from app.monitoring import traceroute

    target = client.get("/api/targets").json()[0]

    async def fake_run(host, **kwargs):
        raise traceroute.TracerouteUnavailable("traceroute is not installed on this system")

    monkeypatch.setattr(traceroute, "run_traceroute", fake_run)
    client.post(f"/api/targets/{target['id']}/traceroute")
    assert target["id"] not in targets_module._traces_in_flight
