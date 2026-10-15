# Internet Monitor

[![CI](https://github.com/duc-mt/internet-monitor/actions/workflows/ci.yml/badge.svg)](https://github.com/duc-mt/internet-monitor/actions/workflows/ci.yml)
[![Python Version](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12%20%7C%203.13-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Code style: ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

A lightweight, self-contained Linux application that continuously measures
Internet latency, packet loss, jitter, and connectivity, alongside on-demand
speed testing — with a local dashboard, a REST API, and a CLI. No cloud
dependency: everything runs and is stored on your own machine.

- **Backend**: Python 3.12 / FastAPI, async monitoring engine, SQLite storage
- **Frontend**: React + TypeScript + Tailwind CSS dashboard
- **CLI**: `internet-monitor` — talks to the same local REST API
- **Packaging**: systemd service, installed via `scripts/install.sh`

---

## Contents

1. [Quick start](#quick-start)
2. [Platform support](#platform-support)
3. [Architecture](#architecture)
4. [Building from source](#building-from-source)
5. [Running](#running)
6. [Installing](#installing)
7. [Uninstalling](#uninstalling)
8. [Configuration](#configuration)
9. [The CLI](#the-cli)
10. [Testing](#testing)
11. [Packaging internals](#packaging-internals)
12. [Troubleshooting](#troubleshooting)
13. [Engineering decisions & known limitations](#engineering-decisions--known-limitations)

---

## Quick start

The fastest way to try it without installing anything system-wide:

### Automatic Launchers (Recommended)

The project includes smart automatic launchers that inspect your system, auto-create `.venv` if missing, install backend & CLI dependencies, build the frontend if missing, and launch the service:

```bash
# Linux / macOS / WSL:
./run.sh                  # Start server and dashboard
./run.sh status           # Run any CLI command directly
./run.sh --help

# Windows (CMD / PowerShell / Double-click):
run.bat                   # Start server and dashboard
run.bat status            # Run CLI command

# Or directly via Python:
python3 run.py            # Linux / macOS
python run.py             # Windows
```

### Manual Setup (Linux / macOS)

```bash
# Backend
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt uvicorn
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8765 &

# Frontend (in another terminal)
cd frontend
npm install
npm run dev   # opens http://127.0.0.1:5173, proxies /api to the backend above
```

### Manual Setup (Windows CMD or PowerShell)

**Prerequisites**: Python 3.12 or 3.13 (Python 3.14+ may trigger Rust compilation errors) and Node.js LTS installed.

```cmd
:: Backend
cd backend
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install --upgrade pip
.venv\Scripts\pip install -r requirements.txt uvicorn
start /B .venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8765

:: Frontend (in a new terminal)
cd frontend
npm install
npm run dev   :: opens http://127.0.0.1:5173, proxies /api to the backend above
```

Or build the frontend once and let the backend serve it on a single port:

```bash
cd frontend && npm install && npm run build && cd ..
cd backend && .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8765
# open http://127.0.0.1:8765
```

**Ad-hoc testing script (`test-site.ps1`)**:
If you are using the `test-scripts\test-site.ps1` script for ad-hoc testing and receive a "running scripts is disabled" error, you can bypass the PowerShell execution policy for that run:
```powershell
powershell -ExecutionPolicy Bypass -File .\test-scripts\test-site.ps1
```

To install permanently as a background service, see [Installing](#installing).

---

## Platform support

**Linux is the primary, fully-supported target** — everything in this repo
(the systemd service, installed via `scripts/install.sh`) is built for and
tested against Linux, per the original brief. Gateway
detection (`/proc/net/route`) and ICMP ping need nothing beyond the base
dependencies. The current-network-name feature additionally needs
`iproute2` (for the wired-interface fallback) and either `wireless-tools`
(`iwgetid`) or NetworkManager (`nmcli`) for the actual Wi-Fi SSID - already
present on virtually every Linux **desktop** install (Ubuntu/Fedora
Desktop, etc.), but not guaranteed on a minimal/server/container image; on
Debian/Ubuntu: `sudo apt install iproute2 wireless-tools`. Without them,
`network_name` is simply `null` - it degrades gracefully rather than
failing anything else.

**How ICMP is sent (Burst Probing).** The monitor no longer shells out to
`ping` for every check: it opens the ICMP socket itself so it can send a
paced burst and time each probe with `perf_counter_ns()` (see
[Burst Probing](#burst-probing-latency-variation-and-stability)).

| OS | Mechanism | Needs |
|---|---|---|
| Linux | unprivileged ICMP datagram socket (`SOCK_DGRAM`), else a raw socket | the service user's group inside `net.ipv4.ping_group_range` (the default on current Ubuntu/Debian/Fedora), **or** `CAP_NET_RAW` (the shipped systemd unit grants it) |
| macOS | unprivileged ICMP datagram socket | nothing |
| Windows | `IcmpSendEcho2` from `iphlpapi.dll` through `ctypes` | nothing (no admin rights) |
| any | TCP handshakes via `asyncio.open_connection` | nothing |

If native ICMP is impossible (a locked-down container, an IPv6-only target)
it degrades to the old `ping` command and then to TCP - one warning is
logged, monitoring never stops. Set `INTERNET_MONITOR_ICMP_ENGINE=ping` to
force the old `ping`-command engine.

**macOS** works for development/ad-hoc use (backend + frontend + CLI in dev
mode — see [Quick start](#quick-start)), with two small platform patches
applied so the core monitoring logic behaves correctly:

- `ping -W` timeout units (Linux = seconds, macOS = milliseconds) — handled
  automatically based on `sys.platform`.
- Desktop notifications use `osascript` (built into macOS) instead of
  `notify-send` (Linux-only) — also automatic.

What does **not** work on macOS, and hasn't been ported:

- The systemd service (`scripts/install.sh`/`uninstall.sh` call
  `useradd`/`systemctl`, which don't exist on macOS) — Linux-specific by
  design.

For ad-hoc testing on macOS (e.g. checking connectivity quality at a
physical location you're visiting), see `test-scripts/test-site.sh` —
it starts the backend with an isolated, disposable dataset per
"site name" and saves a CSV/JSON report when you stop it, which fits
macOS's lack of a background-service option better than trying to install
anything permanently. `test-scripts/test-site.ps1` is the Windows
equivalent, run from PowerShell — see the [Windows](#windows-cmd-or-powershell)
quick-start section below for the execution-policy note it needs.

A native macOS port (a `launchd` background service instead of
`test-site.sh`, a `.pkg` installer) is possible but hasn't been built — the
patches above make development and one-off testing work correctly (ping
timing, notifications, and gateway/network detection all behave correctly
on macOS now), not permanent background operation without a terminal open.

**Windows has a compatibility layer, verified on real hardware.** Every
platform-specific mechanism now has a `win32` branch, built against
documented Windows command syntax and output formats rather than guessed:

- **ICMP ping** builds `ping -n <count> -w <wait_ms> <host>` (Windows'
  actual count/timeout flags - notably `-n` means *count* here, the
  opposite of Linux/macOS - and no `--` separator, which Windows tools
  don't use). Parses both `Reply from X: bytes=32 time=15ms TTL=57` and
  the `Packets: Sent = N, Received = N, Lost = N` summary line, including
  the `time<1ms` sub-millisecond format and Windows-specific failure text
  (`could not find host`, `Destination host unreachable`, `Request timed
  out`, `General failure`).
- **Gateway detection** parses the `0.0.0.0  0.0.0.0  <gateway>` row from
  `route print -4`'s IPv4 route table.
- **Network-name (SSID) detection** parses `SSID` (never `BSSID`, which
  the regex is anchored to exclude) from `netsh wlan show interfaces`
  when connected to Wi-Fi; falls back to a generic `"Wired"` label
  (not a specific adapter name, unlike the macOS/Linux versions - Windows
  has no equally simple single command for that correlation) when there's
  a working default route but no Wi-Fi SSID.
- **Desktop notifications** use Windows PowerShell (bundled with every
  Windows 10/11 install, no module to install) driving the WinRT toast
  API directly. This is the one piece with a known, specific residual
  risk even once it runs: a bare script invocation like this typically
  borrows PowerShell's own AppUserModelID rather than registering its
  own, so the toast may show correctly under "Windows PowerShell" as the
  sender, or be suppressed entirely on a system where a given Windows
  build enforces stricter AUMID requirements or where PowerShell's own
  notifications happen to be disabled in Settings - something only real
  hardware can confirm either way.
- The systemd service and `scripts/install.sh`/`uninstall.sh` remain
  Linux-specific, same as on macOS - there is no Windows service/installer
  equivalent (would be an MSI or a Windows Service wrapper, not attempted).

Everything above is covered by mocked unit tests (exact command
arguments, realistic sample output parsing, escaping) and has been
successfully verified on real Windows environments.

> **Native ICMP status on Windows & macOS:** On macOS, native Burst Probing via
> unprivileged datagram ICMP sockets (`socket(AF_INET, SOCK_DGRAM, IPPROTO_ICMP)`)
> has been tested and verified on real hardware without needing root. On Windows,
> the `IcmpSendEcho2` ctypes binding was exercised against a stand-in `iphlpapi`
> library and falls back to the system `ping` command automatically if needed.
> You can also explicitly set `INTERNET_MONITOR_ICMP_ENGINE=ping` to force
> the subprocess engine.

---

## Architecture

```
internet-monitor/
├── backend/            FastAPI app, monitoring engine, SQLite layer
│   ├── app/
│   │   ├── api/        REST endpoints (targets incl. on-demand traceroute, measurements, statistics, outages, settings, status, monitoring, export, health, speedtest)
│   │   ├── database/   schema.sql + async repositories (aiosqlite)
│   │   ├── monitoring/ burst_prober.py (Burst Probing engine) + burst_stats.py (percentiles, RFC 3550 jitter)
│   │   │               + pinger.py (`ping`-command/TCP fallback) + scheduler.py (per-target async loops) + traceroute.py
│   │   ├── models/     Pydantic request/response/settings models
│   │   ├── services/   statistics, quality classification, outage detection, status,
│   │   │               connectivity, sleep tracking, notifications, settings, speedtest
│   │   ├── spa.py      safe static-file serving for the built frontend
│   │   └── main.py     app wiring, lifespan startup/shutdown
│   └── tests/          pytest, all network calls mocked
├── frontend/           React + TypeScript + Tailwind dashboard (Vite)
├── cli/                `internet-monitor` command-line client (Click + httpx)
├── packaging/
│   └── systemd/        internet-monitor.service (hardened unit)
└── scripts/            install.sh / uninstall.sh (the only install path)
```

**Data flow**: `scheduler.py` runs one async task per enabled target. Each
tick calls `burst_prober.run_burst()` (a paced burst of 10-20 native ICMP or
TCP probes, falling back to the `ping` command and then TCP), reduces it in
memory to a `BurstMetric`, writes one `measurements` row, checks per-target
alert thresholds, then — serialized
behind a lock so concurrent target loops can't race — updates the global
online/offline state and re-evaluates whether an outage should be opened or
closed. The dashboard and CLI both just read this same SQLite-backed state
through the REST API; nothing is computed twice.

**Why the API binds to `127.0.0.1` and never needs root**: on Linux the
monitor first tries an *unprivileged* ICMP datagram socket, which needs no
capability at all; only if the kernel forbids that does it open a raw ICMP
socket, which needs `CAP_NET_RAW` - the shipped systemd unit grants exactly
that one capability (and nothing else) so the service itself never runs as
root. The remaining subprocess calls (`ping` fallback, `traceroute`, network
detection) use `argv`-list `asyncio.create_subprocess_exec` — never
`shell=True` — so there's no shell-injection surface even though hostnames
are user-supplied, and there's no reason for the FastAPI process to be
network-reachable from anywhere but localhost. The static-file route that
serves the dashboard resolves every requested path and refuses anything that
lands outside `frontend/dist` (`app/spa.py`).

---

## Building from source

**Backend**

```bash
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt   # includes uvicorn + test deps
```

**Frontend**

```bash
cd frontend
npm install
npm run build        # → frontend/dist, served by FastAPI in production
# or: npm run dev     # → http://127.0.0.1:5173 with hot reload, proxying /api
```

**CLI**

```bash
cd cli
pip install -e .     # installs the `internet-monitor` command
```

---

## Running

```bash
cd backend
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8765
```

Open `http://127.0.0.1:8765` (if the frontend was built) or
`http://127.0.0.1:8765/docs` for the interactive API reference.

Useful environment variables (all optional):

| Variable | Default | Purpose |
|---|---|---|
| `INTERNET_MONITOR_DATA_DIR` | `~/.local/share/internet-monitor` | Where `internet-monitor.db` lives |
| `INTERNET_MONITOR_HOST` | `127.0.0.1` | API bind address (keep this loopback-only) |
| `INTERNET_MONITOR_PORT` | `8765` | API port |
| `INTERNET_MONITOR_LOG_LEVEL` | `INFO` | Python logging level |
| `INTERNET_MONITOR_AUTOSTART` | `1` | Set to `0` to boot the API without starting monitoring loops |

---

## Installing

```bash
sudo ./scripts/install.sh --enable
```

This creates an unprivileged `internet-monitor` system user, installs to
`/opt/internet-monitor`, sets up a Python virtual environment (fetching
FastAPI/uvicorn/etc. from PyPI — **an internet connection is required at
install time**), installs the systemd unit, and (with `--enable`) enables
+ starts the service immediately. Works on any systemd-based Linux
distribution, not just Debian/Ubuntu.

```bash
sudo systemctl status internet-monitor
internet-monitor status
```

---

## Uninstalling

```bash
sudo ./scripts/uninstall.sh             # keeps data in /var/lib/internet-monitor
sudo ./scripts/uninstall.sh --purge     # also deletes stored history/settings
```

---

## Configuration

Everything in **Settings** on the dashboard (thresholds, notification
preferences, quality-classification boundaries, data retention, theme,
etc.) is stored in the `settings` table and editable at runtime via
`PUT /api/settings` — no restart needed. See `backend/app/models/settings.py`
for the full schema and defaults, or `internet-monitor config get` for the
current values. An example is below:

```json
{
  "ping_timeout_seconds": 2.0,
  "burst_packet_count": 15,
  "burst_interval_ms": 20,
  "default_target_interval_seconds": 60,
  "latency_warning_threshold_ms": 150,
  "packet_loss_warning_threshold_pct": 5,
  "outage_threshold_checks": 3,
  "sleep_gap_threshold_seconds": 60,
  "classification": {
    "excellent_latency_ms": 30, "excellent_packet_loss_pct": 1,
    "good_latency_ms": 60, "good_packet_loss_pct": 2,
    "fair_latency_ms": 100, "fair_packet_loss_pct": 5
  },
  "stability": {
    "excellent_iqr_ms": 5,
    "good_iqr_ms": 15, "good_loss_pct": 7,
    "fair_iqr_ms": 30, "fair_loss_pct": 15
  },
  "raw_retention_days": 7,
  "data_retention_days": 90,
  "theme": "system"
}
```

### Burst Probing: latency, variation and stability

A single ping (or the mean of three) hides what makes a connection *feel*
bad: the spread. Each cycle (default every **60 s** per target) therefore
sends a **burst** of `burst_packet_count` probes (10-20, default 15) spaced
`burst_interval_ms` (15-20 ms) apart, measures every round trip with
`time.perf_counter_ns()`, and reduces the burst in memory - the per-packet
RTTs are never stored - to:

| Metric | Meaning |
|---|---|
| `median_ms` (p50) | the base latency; robust to the odd slow packet |
| `p25_ms`, `p75_ms`, `iqr_ms` | the interquartile range: how widely the *typical* packet scatters |
| `p95_ms` | tail latency inside the burst |
| `min_ms`, `max_ms` | extremes |
| `jitter_rfc3550` | RFC 3550 interarrival jitter: `J += (\|D\| - J) / 16`, `D` = RTT difference between consecutive *answered* probes |
| `packet_loss` | % of the burst's probes that were never answered |

Percentiles use linear interpolation between closest ranks. Two things worth
knowing: the RFC's `1/16` gain means a 15-probe burst only partly converges
from its zero start, so `jitter_rfc3550` reads lower than the plain mean of
`|D|` (it is a smoothed per-burst indicator, as the RFC defines it); and one
lost probe of 15 is 6.67 % loss, so a single burst's loss is coarse - read it
over a range.

The legacy `latency_ms` / `jitter_ms` columns mirror `median_ms` /
`jitter_rfc3550`, so older readers (and CSV consumers) keep working; the CSV
export appends the new columns after the old ones.

**Stability score** (Dashboard) rates the latest burst by variation and loss,
independent of how *low* the latency is: **Excellent** = no loss and IQR below
`stability.excellent_iqr_ms` (5 ms); **Good** = loss up to 7 % (one lost probe)
and IQR < 15 ms; **Fair** = loss up to 15 % and IQR < 30 ms; **Poor** = worse.
All five boundaries are configurable.

**The smoke graph** draws the selected target's median as a line over two
bands - IQR (p25-p75) and tail (min-p95) - with packet loss as red bars, for
5 m / 15 m / 1 h / 6 h / 24 h on the Dashboard (and up to 30 d on History).
Long ranges are thinned into time buckets in the browser, keeping each
bucket's *worst* tail so a spike is never averaged away.

> **Outage *records* now take minutes, not seconds.** The Online/Offline
> indicator and the "connection lost" notification follow the latest burst
> (so they react within one cycle), but an outage is only *recorded* - added to
> the outage log, traceroute captured, long-outage alert armed - after
> `outage_threshold_checks` (default 3) consecutive failed **checks**. A check
> is now one per minute, so that is roughly 3 minutes (it was ~15 s at the old
> 5 s cadence). Lower it to 1-2, or shorten a target's interval, if you want
> faster detection - at the cost of more rows (below).

### Storage: two tiers, bounded size

| Tier | Holds | Kept |
|---|---|---|
| `measurements` | one row per burst (full summary above) | `raw_retention_days` (default **7**) |
| `ping_metrics_hourly` | one row per target per UTC hour: `avg_median_ms`, `avg_iqr_ms`, `max_p95_ms`, `avg_loss_pct`, `sample_count` (+ `min_ms`, `max_ms`, `avg_jitter_ms`) | `data_retention_days` (default **90**) |

An hourly background task folds raw rows older than the cutoff into the
hourly tier (in one transaction with the delete, so nothing is lost or counted
twice; the cutoff is floored to the hour so an hour is never split), drops
hourly rows past retention, compacts the file if a large rollup left a lot of
free space, and truncates the WAL. The History page, statistics and CSV export
read across both tiers; hourly rows come back flagged `error = "Downsampled"`.
Statistics over ranges that reach into the hourly tier are weighted by
`sample_count`, and their median/p95 are approximations built from hourly
aggregates (the raw RTTs are gone).

The connection is opened with `journal_mode=WAL`, `synchronous=NORMAL` and
`temp_store=MEMORY`.

**Measured size** (90 simulated days, the real daily rollup cycle, 5 targets at
the default 60 s): **13.8 MB** in total - about 2.2 MB per target for the 7 raw
days (~215 B/row incl. indexes) plus ~0.3 MB for 83 hourly days (~140 B/row).
That puts the default configuration under 50 MB up to **about 20 targets**.
The size scales linearly with `targets / interval`: a 30 s interval halves that
capacity, a 5 s interval is 12x the rows. An install upgraded from the old
5-second checks still holds up to 7 days of those rows until they age out
(the old default kept them just as long); the first big rollup is followed by
a one-time `VACUUM`, which briefly needs spare disk space.

**Upgrading**: new columns and the hourly table are added automatically. Once,
on first start, targets still on the old 5 s default interval move to 60 s, a
stored `default_target_interval_seconds` of 5 becomes 60, and a stored
`data_retention_days` of 30 (the old default) becomes 90; values you set
yourself are left alone, and the old `pings_per_check` setting is dropped.

**SLA error budget.** Set `sla_target_pct` (e.g. `99.9`, the uptime in your
ISP contract) and the Dashboard (rolling 30 days) and History (selected
range) show how much of the allowed downtime is used: monitored time x
(1 - SLA/100), amber from 80% used, red once it is exceeded. Monitored time
excludes detected sleep gaps, the same denominator as the uptime percentage.

**Webhook alerts.** Set `notifications.webhook_url` to also POST every alert
to Slack, Discord or any endpoint that accepts JSON — useful on a headless
server with no desktop to notify. The payload shape is chosen from the URL
(Slack: `text`; Discord: `content`; anything else: `text`, `title`,
`message`, `urgency`). Delivery is best-effort with a 10 s timeout and never
blocks monitoring. Slack and Discord URLs contain a secret token, so the API
never returns or logs it in full — `GET`/`PUT /api/settings` show it masked
as `scheme://host/\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022` (e.g. `https://hooks.slack.com/\u2022\u2022\u2022\u2022\u2022\u2022\u2022\u2022`).
Saving settings with that masked value still in the field leaves the real
URL untouched; type a new URL (or clear the field) to actually change it.

**Targets** (which hosts are monitored) are managed separately via the
Targets page, the `/api/targets` endpoints, or `internet-monitor targets`.
Four defaults are seeded on first run: your detected gateway, your WAN IP
(detected automatically), Google DNS (`8.8.8.8`), and Cloudflare DNS (`1.1.1.1`).

**Start on boot**: the dashboard's toggle only records a preference — the
app never grants itself permission to change systemd state. Actually
enabling/disabling the boot-time service is a deliberate, explicit step:

```bash
internet-monitor service enable-boot     # sudo systemctl enable --now internet-monitor
internet-monitor service disable-boot    # sudo systemctl disable internet-monitor
```

---

## The CLI

```
internet-monitor status [--json]
internet-monitor start
internet-monitor stop
internet-monitor targets list
internet-monitor targets add NAME HOST [--protocol icmp|tcp] [--port N] [--interval SECONDS] [--gateway] [--disabled]
internet-monitor targets edit TARGET_ID [--name] [--host] [--protocol] [--port] [--interval] [--enable/--disable]
internet-monitor targets remove TARGET_ID
internet-monitor history [--target ID] [--range 1h|24h|7d|30d] [--limit N]
internet-monitor export --format csv|json [--target ID] [--range ...] [-o FILE]
internet-monitor config get [KEY]
internet-monitor config set KEY VALUE
internet-monitor service enable-boot|disable-boot
```

It's a thin client — every command calls the same local REST API the
dashboard uses (default `http://127.0.0.1:8765/api`, override with
`--api-url` or `INTERNET_MONITOR_API_URL`). It never touches the database
or performs pings itself.

---

## Testing

**Backend** (~280 tests plus 10 for the CLI; nothing needs real Internet access — probes run
against fake sockets, loopback or an ephemeral local server):

```bash
cd backend
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q --cov=app --cov-report=term-missing
```

**Frontend** (~110 tests: formatting helpers, the API client's error
handling, smoke-graph data/bucketing, component rendering/empty-states, and a
mocked-API Dashboard integration test; jsdom cannot draw Recharts' SVG, so the
plotted shapes are checked in a real browser, not here):

```bash
cd frontend
npm test
```

Both suites are also exercised end-to-end manually during development
against a real running backend (real ICMP pings, real TCP fallback, real
outage detection) — see the CLI section above for the exact commands.

---

## Packaging internals

- **systemd** (`packaging/systemd/internet-monitor.service`), installed by
  `scripts/install.sh`: see the
  comments in the unit file for the capability/hardening reasoning
  (short version: `NoNewPrivileges=true` + `ProtectSystem=strict` +
  everything else locked down, with exactly one capability —
  `CAP_NET_RAW` — granted via `AmbientCapabilities` so the monitor can open
  its ICMP socket (and the `ping` fallback still works) without the service
  running as root or relying on `ping` being setuid on the host distro).

---

## Troubleshooting

**"Could not reach the Internet Monitor service"** (CLI or dashboard) — the
backend isn't running, or is bound somewhere other than what you're asking.
Check `sudo systemctl status internet-monitor` (packaged install) or that
your manual `uvicorn` process is still alive; check `INTERNET_MONITOR_PORT`
matches what the client expects.

**All targets show 100% loss / "ICMP not permitted"** — some
containers/sandboxes block raw sockets entirely, even for `CAP_NET_RAW`
processes. The app automatically falls back to TCP checks the first time
ICMP fails outright (logged once, not on every check) — if it doesn't,
confirm the `ping` binary exists at all (`which ping`; on minimal images
you may need `apt install iputils-ping`).

**No desktop notifications** — Internet Monitor calls `notify-send`
(`libnotify-bin`) rather than bundling a notification library. If it's not
installed, notifications are logged instead of shown; `sudo apt install
libnotify-bin` and restart the service.

**Traceroute says "traceroute is not installed"** — the Route button on the
Targets page and dashboard runs the system `traceroute` (`tracert` on
Windows). Minimal Linux images often lack it: `sudo apt install traceroute`.
A hop shown as `* * *` is usually a router that ignores ICMP, not a fault; it
only matters when the hops after it are lost too.

**Dashboard shows "Frontend build not found"** — you're running the backend
without having built the frontend first. Run `npm run build` in `frontend/`,
or use `npm run dev` for a hot-reloading dev server on port 5173.

**"database is locked" or similar SQLite errors** — shouldn't happen in
normal operation (writes are serialized through a single connection +
lock), but if you see it, check that nothing else has the database file
open (e.g. a second instance of the backend pointed at the same
`INTERNET_MONITOR_DATA_DIR`).

**Journal logs**: `journalctl -u internet-monitor -f` for a packaged
install.

**Windows: `httpx.ConnectError: [SSL: CERTIFICATE_VERIFY_FAILED]` during backend install** — You are likely using a pre-release Python version (e.g., 3.14). Core dependencies like `pydantic-core` lack pre-compiled wheels (`.whl`) for unreleased Python versions, forcing `pip` to compile from source via Rust, which fails behind some SSL configurations. Rollback and use a stable version like Python 3.12 or 3.13 (`py -3.12 -m venv .venv`).

**Windows: `'npm' is not recognized as an internal or external command`** — Node.js is not installed or not in your system `PATH`. Download the LTS installer from `nodejs.org`. Ensure the **Add to PATH** option is selected during setup. **Do not** check the option to automatically install "Tools for Native Modules" (Chocolatey / C++ Build Tools) as it is unnecessary and may cause environment conflicts. Open a completely new terminal after installation.

**Windows: `Error: connect ECONNREFUSED 127.0.0.1:8765` in frontend logs** — The Vite development server proxy cannot reach the FastAPI backend. Ensure the backend process is actively running on port 8765 in a separate terminal. If the backend crashed with `[Errno 10048] error while attempting to bind on address`, free the port by finding the zombie PID (`netstat -ano | findstr :8765`) and terminating it (`taskkill /PID <PID> /F`).

---

## Engineering decisions & known limitations

The brief asked for reasonable engineering decisions to be made and
documented where it left things unspecified. Here's what was decided and
why:

- **A check is a burst, summarised in memory.** Each "check" sends 10-20
  paced probes (see [Burst Probing](#burst-probing-latency-variation-and-stability)),
  and one `measurements` row stores the burst's median / quartiles / p95 /
  min / max / RFC 3550 jitter / loss. Aggregate statistics over a time range
  are then computed across many such rows (and, past `raw_retention_days`,
  the hourly tier). `latency_ms` is the *median*, not the mean, since the
  rewrite.
- **The gateway is excluded from outage detection.** An outage is recorded
  when every enabled *non-gateway* target fails for `outage_threshold_checks`
  checks in a row. A dead gateway means your LAN is down, which is real but
  different from "the Internet is down," and conflating the two would make
  the outage log noisy for anyone on flaky Wi-Fi. The instantaneous
  Online/Offline indicator, by contrast, considers *all* enabled targets
  (gateway included) — it answers a different, more immediate question.
- **Headline latency/loss/jitter on the status view are averaged across
  non-gateway targets.** The gateway is typically a ~1ms local hop and
  isn't representative of "Internet" quality.
- **Native-ICMP fallbacks are logged once, not stamped onto every
  measurement.** If native ICMP can't work (no permission, a container
  without raw sockets, an unexpected error) the process drops to the `ping`
  command and then to TCP for the rest of its life and logs it a single
  time — it doesn't decorate every subsequent successful measurement's
  `error` field with a "used TCP instead" note forever.
- **The systemd unit needs `CAP_NET_RAW` for ICMP under `NoNewPrivileges`.**
  See the packaging section above and the unit file's comments.
- **The "Start on boot" setting never lets the app self-elevate.** It's
  purely a stored preference; actually changing systemd's enabled state is
  a separate, explicit `internet-monitor service enable-boot` command that
  shells out to `sudo systemctl` and will prompt for a password
  interactively. The API/dashboard process itself never gains, requests,
  or needs elevated privileges to do this.
- **`scripts/install.sh` fetches dependencies from PyPI at install time**
  rather than vendoring wheels, keeping the repo itself small and simple
  at the cost of requiring network access during install. For a fully
  offline install, `pip download` the requirements yourself ahead of
  time and point `pip install` at that local cache instead.
- **macOS SSID detection has two fallback layers.** `networksetup
  -getairportnetwork` is tried first (fast), but Apple disabled it from
  returning a real SSID at all starting with macOS 15/Sequoia (a
  deliberate Location Services privacy restriction, confirmed via
  macadmin community reports - not something fixable from this side).
  `system_profiler SPAirPortDataType` isn't subject to that restriction
  and is used as a fallback when the fast path fails - it's noticeably
  slower (spawns a heavier process), which is fine given the whole
  network-name result is cached for 30s regardless of which method
  produced it.
- **Gateway auto-detection is a genuinely different mechanism per platform,
  not a shared code path.** Linux reads `/proc/net/route` directly (no
  subprocess needed); macOS has no `/proc` filesystem, so it shells out to
  `route -n get default` instead. Both fall back to `192.168.1.1` if
  detection fails for any reason, rather than leaving the seeded Gateway
  target with an empty/invalid host.
- **Desktop notifications use `notify-send`** (a call to the standard
  `libnotify` CLI tool) rather than a Python GUI-toolkit binding, so the
  monitoring service has zero GUI dependencies and runs identically
  headless or on a desktop.
- **Sleep/wake detection is a single wall-clock-gap heuristic, not OS power
  events.** A gap between two consecutive monitoring ticks larger than
  `sleep_gap_threshold_seconds` (default 60s) is recorded as a
  `system_sleep` event and excluded from downtime/uptime% - see
  `app/services/sleep_service.py`. This correctly catches a full OS
  suspend (the process is frozen, so no failed checks get written at all,
  just a gap). It does **not** catch the rarer case where the OS keeps the
  process running but tears down networking during sleep (some laptops'
  lid-close/"Power Nap" behavior) - that would need macOS
  IOKit/Linux D-Bus login1 power-event hooks, deliberately out of scope
  for how cheap and OS-agnostic this heuristic is.
