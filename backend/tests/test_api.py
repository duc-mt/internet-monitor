from __future__ import annotations


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
    create_resp = client.post("/api/targets", json={
        "name": "Custom Host", "host": "example.com", "protocol": "tcp", "port": 443, "interval_seconds": 10,
    })
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
        "online", "quality", "targets_reachable", "targets_total", "targets", "monitoring_running",
        "network_name", "uptime_pct_24h",
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
