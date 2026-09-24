"""
internet-monitor: command-line interface.

This is a thin client over the local REST API (default
http://127.0.0.1:8765/api) - it never touches the database or performs
pings itself, so `internet-monitor status` always reflects exactly what the
dashboard would show.
"""

from __future__ import annotations

import json as jsonlib
import subprocess
import sys
from typing import Any

import click
import httpx

DEFAULT_API_URL = "http://127.0.0.1:8765/api"


class ApiClient:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")

    def _request(self, method: str, path: str, **kwargs) -> Any:
        try:
            resp = httpx.request(method, f"{self.base_url}{path}", timeout=10.0, **kwargs)
        except httpx.ConnectError:
            raise click.ClickException(
                f"Could not reach the Internet Monitor service at {self.base_url}.\n"
                f"  Is it running? Try: sudo systemctl status internet-monitor\n"
                f"  Or, if running manually: uvicorn app.main:app (see README)."
            )
        except httpx.TimeoutException:
            raise click.ClickException("Request to the Internet Monitor service timed out.")
        if resp.status_code >= 400:
            detail = resp.text
            try:
                detail = resp.json().get("detail", detail)
            except Exception:
                pass
            raise click.ClickException(f"API error {resp.status_code}: {detail}")
        if resp.status_code == 204 or not resp.content:
            return None
        return resp.json()

    def get(self, path: str, **kwargs) -> Any:
        return self._request("GET", path, **kwargs)

    def post(self, path: str, **kwargs) -> Any:
        return self._request("POST", path, **kwargs)

    def put(self, path: str, **kwargs) -> Any:
        return self._request("PUT", path, **kwargs)

    def delete(self, path: str, **kwargs) -> Any:
        return self._request("DELETE", path, **kwargs)


def print_table(rows: list[dict], columns: list[str] | None = None) -> None:
    if not rows:
        click.echo("(none)")
        return
    cols = columns or list(rows[0].keys())
    widths = {c: max(len(c), *(len(str(r.get(c, ""))) for r in rows)) for c in cols}
    header = "  ".join(c.upper().ljust(widths[c]) for c in cols)
    click.echo(header)
    click.echo("  ".join("-" * widths[c] for c in cols))
    for r in rows:
        click.echo("  ".join(str(r.get(c, "")).ljust(widths[c]) for c in cols))


@click.group()
@click.option(
    "--api-url",
    default=DEFAULT_API_URL,
    envvar="INTERNET_MONITOR_API_URL",
    help="Base URL of the Internet Monitor API.",
    show_default=True,
)
@click.pass_context
def cli(ctx: click.Context, api_url: str):
    """Command-line interface for Internet Monitor."""
    ctx.obj = ApiClient(api_url)


# --------------------------------------------------------------------------
# status
# --------------------------------------------------------------------------
@cli.command()
@click.option("--json", "as_json", is_flag=True, help="Print raw JSON instead of a summary.")
@click.pass_obj
def status(client: ApiClient, as_json: bool):
    """Show current connectivity status."""
    data = client.get("/status")
    if as_json:
        click.echo(jsonlib.dumps(data, indent=2))
        return

    state = "ONLINE" if data["online"] else "OFFLINE"
    color = "green" if data["online"] else "red"
    click.echo(f"Internet: {click.style(state, fg=color, bold=True)}  (quality: {data['quality']})")
    click.echo(f"Latency:     {_fmt_ms(data['latency_ms'])}")
    click.echo(f"Packet loss: {_fmt_pct(data['packet_loss'])}")
    click.echo(f"Jitter:      {_fmt_ms(data['jitter_ms'])}")
    click.echo(f"Targets reachable: {data['targets_reachable']}/{data['targets_total']}")
    click.echo(
        f"Monitoring: {'running' if data['monitoring_running'] else 'stopped'} "
        f"(uptime {int(data['monitoring_uptime_seconds'])}s)"
    )
    if data["active_outage"]:
        click.echo(click.style("An outage is currently in progress.", fg="red"))


def _fmt_ms(v: float | None) -> str:
    return "—" if v is None else f"{v:.1f} ms"


def _fmt_pct(v: float | None) -> str:
    return "—" if v is None else f"{v:.1f}%"


# --------------------------------------------------------------------------
# start / stop
# --------------------------------------------------------------------------
@cli.command()
@click.pass_obj
def start(client: ApiClient):
    """Start the monitoring loops."""
    result = client.post("/monitoring/start")
    click.echo("Monitoring started." if result["running"] else "Monitoring did not start.")


@cli.command()
@click.pass_obj
def stop(client: ApiClient):
    """Stop the monitoring loops."""
    result = client.post("/monitoring/stop")
    click.echo("Monitoring stopped." if not result["running"] else "Monitoring is still running.")


# --------------------------------------------------------------------------
# targets
# --------------------------------------------------------------------------
@cli.group()
def targets():
    """Manage monitored targets."""


@targets.command("list")
@click.pass_obj
def targets_list(client: ApiClient):
    """List all configured targets."""
    rows = client.get("/targets")
    print_table(
        [
            {
                "id": t["id"],
                "name": t["name"],
                "host": t["host"],
                "protocol": t["protocol"],
                "interval": f"{t['interval_seconds']}s",
                "enabled": t["enabled"],
                "gateway": t["is_gateway"],
            }
            for t in rows
        ]
    )


@targets.command("add")
@click.argument("name")
@click.argument("host")
@click.option("--protocol", type=click.Choice(["icmp", "tcp"]), default="icmp", show_default=True)
@click.option(
    "--port", type=int, default=None, help="TCP port (required for --protocol tcp unless you want the default of 443)."
)
@click.option("--interval", type=int, default=5, show_default=True, help="Seconds between checks.")
@click.option("--gateway", is_flag=True, help="Mark as the local gateway (excluded from outage detection).")
@click.option("--disabled", is_flag=True, help="Create the target disabled.")
@click.pass_obj
def targets_add(client: ApiClient, name, host, protocol, port, interval, gateway, disabled):
    """Add a new monitored target, e.g. `internet-monitor targets add "Office WAN" 203.0.113.5`."""
    payload = {
        "name": name,
        "host": host,
        "protocol": protocol,
        "port": port,
        "interval_seconds": interval,
        "is_gateway": gateway,
        "enabled": not disabled,
    }
    created = client.post("/targets", json=payload)
    click.echo(f"Created target #{created['id']} ({created['name']}).")


@targets.command("edit")
@click.argument("target_id", type=int)
@click.option("--name", default=None)
@click.option("--host", default=None)
@click.option("--protocol", type=click.Choice(["icmp", "tcp"]), default=None)
@click.option("--port", type=int, default=None)
@click.option("--interval", type=int, default=None)
@click.option("--enable/--disable", "enabled", default=None)
@click.pass_obj
def targets_edit(client: ApiClient, target_id, name, host, protocol, port, interval, enabled):
    """Edit fields of an existing target by id."""
    payload = {
        k: v
        for k, v in {
            "name": name,
            "host": host,
            "protocol": protocol,
            "port": port,
            "interval_seconds": interval,
            "enabled": enabled,
        }.items()
        if v is not None
    }
    if not payload:
        raise click.UsageError("Provide at least one field to change.")
    updated = client.put(f"/targets/{target_id}", json=payload)
    click.echo(f"Updated target #{updated['id']} ({updated['name']}).")


@targets.command("remove")
@click.argument("target_id", type=int)
@click.confirmation_option(prompt="Delete this target and its measurement history?")
@click.pass_obj
def targets_remove(client: ApiClient, target_id):
    """Delete a target."""
    client.delete(f"/targets/{target_id}")
    click.echo(f"Deleted target #{target_id}.")


# --------------------------------------------------------------------------
# history
# --------------------------------------------------------------------------
@cli.command()
@click.option("--target", "target_id", type=int, default=None, help="Filter by target id.")
@click.option("--range", "range_name", default="24h", type=click.Choice(["1h", "24h", "7d", "30d"]), show_default=True)
@click.option("--limit", type=int, default=20, show_default=True)
@click.pass_obj
def history(client: ApiClient, target_id, range_name, limit):
    """Show recent measurements and a summary for the chosen range."""
    stats = client.get("/statistics", params={"range": range_name, **({"target_id": target_id} if target_id else {})})
    click.echo(f"Statistics ({range_name}):")
    click.echo(
        f"  avg={_fmt_ms(stats['avg_latency_ms'])}  min={_fmt_ms(stats['min_latency_ms'])}  "
        f"max={_fmt_ms(stats['max_latency_ms'])}  p95={_fmt_ms(stats['p95_latency_ms'])}"
    )
    click.echo(
        f"  packet loss={_fmt_pct(stats['packet_loss_pct'])}  jitter={_fmt_ms(stats['avg_jitter_ms'])}  "
        f"outages={stats['outage_count']}  samples={stats['sample_count']}"
    )
    click.echo()

    params = {"limit": limit}
    if target_id:
        params["target_id"] = target_id
    rows = client.get("/measurements", params=params)
    print_table(
        [
            {
                "time": m["timestamp"],
                "target": m.get("target_name", m["target_id"]),
                "latency_ms": m["latency_ms"],
                "loss%": m["packet_loss"],
                "success": m["success"],
            }
            for m in rows
        ]
    )


# --------------------------------------------------------------------------
# export
# --------------------------------------------------------------------------
@cli.command()
@click.option("--format", "fmt", type=click.Choice(["csv", "json"]), default="csv", show_default=True)
@click.option("--target", "target_id", type=int, default=None)
@click.option(
    "--range",
    "range_name",
    default="24h",
    type=click.Choice(["1h", "24h", "7d", "30d"]),
    show_default=True,
    help="Only used for --format json (the summarized report).",
)
@click.option("--output", "-o", type=click.Path(), default=None, help="Write to this file instead of stdout.")
@click.pass_obj
def export(client: ApiClient, fmt, target_id, range_name, output):
    """Export measurement data as CSV, or a summarized report as JSON."""
    if fmt == "csv":
        params = {"target_id": target_id} if target_id else {}
        resp = httpx.get(f"{client.base_url}/export/measurements.csv", params=params, timeout=30.0)
        content = resp.text
    else:
        params = {"range": range_name, **({"target_id": target_id} if target_id else {})}
        resp = httpx.get(f"{client.base_url}/export/report.json", params=params, timeout=30.0)
        content = resp.text

    if output:
        with open(output, "w") as f:
            f.write(content)
        click.echo(f"Wrote {output}")
    else:
        click.echo(content)


# --------------------------------------------------------------------------
# config
# --------------------------------------------------------------------------
@cli.group()
def config():
    """View or change monitoring settings."""


@config.command("get")
@click.argument("key", required=False)
@click.pass_obj
def config_get(client: ApiClient, key: str | None):
    """Print all settings, or a single dotted key (e.g. notifications.on_offline)."""
    data = client.get("/settings")
    if key is None:
        click.echo(jsonlib.dumps(data, indent=2))
        return
    value = _dotted_get(data, key)
    click.echo(jsonlib.dumps(value) if isinstance(value, (dict, list)) else value)


@config.command("set")
@click.argument("key")
@click.argument("value")
@click.pass_obj
def config_set(client: ApiClient, key: str, value: str):
    """Set a single dotted key, e.g. `config set data_retention_days 60`."""
    parsed = _parse_scalar(value)
    payload = _dotted_set({}, key, parsed)
    updated = client.put("/settings", json=payload)
    click.echo(f"{key} = {_dotted_get(updated, key)}")


def _dotted_get(data: dict, key: str) -> Any:
    node = data
    for part in key.split("."):
        if not isinstance(node, dict) or part not in node:
            raise click.ClickException(f"Unknown setting: {key}")
        node = node[part]
    return node


def _dotted_set(root: dict, key: str, value: Any) -> dict:
    parts = key.split(".")
    node = root
    for part in parts[:-1]:
        node = node.setdefault(part, {})
    node[parts[-1]] = value
    return root


def _parse_scalar(raw: str) -> Any:
    lowered = raw.lower()
    if lowered in ("true", "false"):
        return lowered == "true"
    try:
        return int(raw)
    except ValueError:
        pass
    try:
        return float(raw)
    except ValueError:
        pass
    return raw


# --------------------------------------------------------------------------
# service (systemd boot integration - the one place the CLI needs sudo,
# and only when the user explicitly asks for it)
# --------------------------------------------------------------------------
@cli.group()
def service():
    """Manage the systemd service (start on boot)."""


@service.command("enable-boot")
def service_enable_boot():
    """Enable the internet-monitor systemd service at boot (prompts for sudo)."""
    _run_systemctl(["enable", "--now", "internet-monitor.service"])


@service.command("disable-boot")
def service_disable_boot():
    """Disable the internet-monitor systemd service at boot (prompts for sudo)."""
    _run_systemctl(["disable", "internet-monitor.service"])


def _run_systemctl(args: list[str]) -> None:
    cmd = ["sudo", "systemctl", *args]
    click.echo(f"Running: {' '.join(cmd)}")
    try:
        subprocess.run(cmd, check=True)
    except FileNotFoundError:
        raise click.ClickException("systemctl not found - this command only works on systemd-based Linux systems.")
    except subprocess.CalledProcessError as exc:
        raise click.ClickException(f"systemctl exited with status {exc.returncode}.")


def main() -> None:
    cli(auto_envvar_prefix="INTERNET_MONITOR")


if __name__ == "__main__":
    sys.exit(cli())
