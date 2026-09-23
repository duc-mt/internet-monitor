# Internet Monitor

A lightweight, self-contained Linux application that continuously measures
Internet latency, packet loss, jitter, and connectivity — with a local
dashboard, a REST API, and a CLI. No cloud dependency: everything runs and
is stored on your own machine.

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

### Linux / macOS

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

### Windows (CMD or PowerShell)

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
physical location you're visiting), see `test-site.sh` at the project
root — it starts the backend with an isolated, disposable dataset per
"site name" and saves a CSV/JSON report when you stop it, which fits
macOS's lack of a background-service option better than trying to install
anything permanently. `test-site.ps1` (same project root) is the Windows
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

---

## Architecture

```
internet-monitor/
├── backend/            FastAPI app, monitoring engine, SQLite layer
│   ├── app/
│   │   ├── api/        REST endpoints (targets, measurements, statistics, outages, settings, status, monitoring, export, health)
│   │   ├── database/   schema.sql + async repositories (aiosqlite)
│   │   ├── monitoring/ pinger.py (ICMP/TCP probes) + scheduler.py (per-target async loops)
│   │   ├── models/     Pydantic request/response/settings models
│   │   ├── services/   statistics, quality classification, outage detection,
│   │   │               connectivity tracking, notifications, settings cache
│   │   └── main.py     app wiring, lifespan startup/shutdown, static frontend mount
│   └── tests/          pytest, all network calls mocked
├── frontend/           React + TypeScript + Tailwind dashboard (Vite)
├── cli/                `internet-monitor` command-line client (Click + httpx)
├── packaging/
│   └── systemd/        internet-monitor.service (hardened unit)
└── scripts/            install.sh / uninstall.sh (the only install path)
```

**Data flow**: `scheduler.py` runs one async task per enabled target. Each
tick calls `pinger.run_check()` (real ICMP via the system `ping` binary,
falling back to a raw TCP connect if ICMP isn't available), writes a
`measurements` row, checks per-target alert thresholds, then — serialized
behind a lock so concurrent target loops can't race — updates the global
online/offline state and re-evaluates whether an outage should be opened or
closed. The dashboard and CLI both just read this same SQLite-backed state
through the REST API; nothing is computed twice.

**Why the API binds to `127.0.0.1` and never needs root**: the monitoring
process never opens a raw socket itself. It shells out to the system `ping`
binary (which is what actually needs `CAP_NET_RAW`) using `argv`-list
`subprocess`/`asyncio.create_subprocess_exec` calls — never `shell=True` —
so there's no shell-injection surface even though hostnames are
user-supplied, and no reason for the FastAPI process itself to run as root
or be network-reachable from anywhere but localhost.

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
  "pings_per_check": 3,
  "latency_warning_threshold_ms": 150,
  "packet_loss_warning_threshold_pct": 5,
  "outage_threshold_checks": 3,
  "sleep_gap_threshold_seconds": 60,
  "classification": {
    "excellent_latency_ms": 30, "excellent_packet_loss_pct": 1,
    "good_latency_ms": 60, "good_packet_loss_pct": 2,
    "fair_latency_ms": 100, "fair_packet_loss_pct": 5
  },
  "data_retention_days": 30,
  "theme": "system"
}
```

**Targets** (which hosts are monitored) are managed separately via the
Targets page, the `/api/targets` endpoints, or `internet-monitor targets`.
Three defaults are seeded on first run: your detected gateway, Cloudflare
DNS (`1.1.1.1`), and Google DNS (`8.8.8.8`).

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

**Backend** (68 tests, no real network access required — every subprocess
and socket call is mocked or points at an ephemeral local server):

```bash
cd backend
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q --cov=app --cov-report=term-missing
```

**Frontend** (32 tests: formatting helpers, the API client's error
handling, component rendering/empty-states, and a mocked-API Dashboard
integration test):

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
  `CAP_NET_RAW` — granted via `AmbientCapabilities` so ICMP still works
  without the service running as root or relying on `ping` being
  setuid on the host distro).

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

- **A check is a small batch, not a single ping.** Each "check" sends
  `pings_per_check` (default 3) ICMP echoes or TCP connection attempts in
  one go, and the stored `latency_ms`/`jitter_ms`/`packet_loss` for that
  measurement row are the average, mean-absolute-successive-difference, and
  loss % *within that batch*. This is what makes a meaningful per-check
  jitter and loss percentage possible at all — a single ping can't have
  "jitter." Aggregate statistics (min/max/median/p95 over a time range) are
  then computed across many such rows.
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
- **ICMP-unavailable fallback is logged once, not stamped onto every
  measurement.** If the `ping` binary is missing or blocked, the app
  permanently switches that process's checks to TCP and logs it a single
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
