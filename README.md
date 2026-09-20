# Internet Monitor

A lightweight, self-contained Linux application that continuously measures
Internet latency, packet loss, jitter, and connectivity — with a local
dashboard, a REST API, and a CLI. No cloud dependency: everything runs and
is stored on your own machine.

- **Backend**: Python 3.12 / FastAPI, async monitoring engine, SQLite storage
- **Frontend**: React + TypeScript + Tailwind CSS dashboard
- **CLI**: `internet-monitor` — talks to the same local REST API
- **Packaging**: systemd service, `.deb`, and a portable AppImage

---

## Contents

1. [Quick start](#quick-start)
2. [Platform support](#platform-support)
3. [Architecture](#architecture)
4. [Building from source](#building-from-source)
5. [Running](#running)
6. [Installing (deb / AppImage / manual)](#installing)
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
(the systemd service, the `.deb` package, the AppImage, `scripts/install.sh`)
is built for and tested against Linux, per the original brief.

**macOS** works for development/ad-hoc use (backend + frontend + CLI in dev
mode — see [Quick start](#quick-start)), with two small platform patches
applied so the core monitoring logic behaves correctly:

- `ping -W` timeout units (Linux = seconds, macOS = milliseconds) — handled
  automatically based on `sys.platform`.
- Desktop notifications use `osascript` (built into macOS) instead of
  `notify-send` (Linux-only) — also automatic.

What does **not** work on macOS, and hasn't been ported:

- The systemd service, `.deb` package, and AppImage — Linux-specific by
  design (AppImage in particular is a Linux binary format and fails with
  `exec format error` if you try to run it on a Mac).
- `scripts/install.sh` / `uninstall.sh` — call `useradd`/`systemctl`, which
  don't exist on macOS.
- Gateway auto-detection reads `/proc/net/route` (Linux-only); on macOS it
  silently falls back to a generic placeholder IP rather than your actual
  default gateway.

For ad-hoc testing on macOS (e.g. checking connectivity quality at a
physical location you're visiting), see `test-site.sh` at the project
root — it starts the backend with an isolated, disposable dataset per
"site name" and saves a CSV/JSON report when you stop it, which fits
macOS's lack of a background-service option better than trying to install
anything permanently.

A native macOS port (a `launchd` background service instead of
`test-site.sh`, a `.pkg` installer, `route get default` for real gateway
detection) is possible but hasn't been built — the two patches above make
development and one-off testing work correctly, not permanent background
operation.

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
│   ├── systemd/        internet-monitor.service (hardened unit)
│   ├── deb/            debian control files + build.sh
│   └── appimage/       AppRun + .desktop + icon + build.sh
└── scripts/            install.sh / uninstall.sh (manual, non-package install)
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

### Option A — Debian package (recommended on Debian/Ubuntu)

```bash
./packaging/deb/build.sh           # builds frontend if needed, produces dist/internet-monitor_1.0.0_all.deb
sudo apt install ./dist/internet-monitor_1.0.0_all.deb
```

This creates an unprivileged `internet-monitor` system user, installs to
`/opt/internet-monitor`, sets up a Python virtual environment (fetching
FastAPI/uvicorn/etc. from PyPI — **an internet connection is required at
install time**), installs the systemd unit, and enables + starts the
service immediately.

```bash
sudo systemctl status internet-monitor
internet-monitor status
```

### Option B — AppImage (portable, no install, no root)

```bash
./packaging/appimage/build.sh      # produces dist/Internet-Monitor-<arch>.AppImage
./dist/Internet-Monitor-x86_64.AppImage
```

This starts the server in the foreground, opens the dashboard in your
default browser, and stops when you press Ctrl+C. It does **not** register
a systemd service or run on boot — that's what Option A is for. It's meant
for trying the app out or running it ad hoc. You can also drive the bundled
CLI without installing anything: `./Internet-Monitor-x86_64.AppImage --cli status`.

Building an AppImage requires network access once, to fetch `appimagetool`
from GitHub releases (cached under `packaging/appimage/build/` afterward).
The AppImage bundles pure-Python dependencies but runs them with the
**system** `python3` (≥3.10) rather than an embedded interpreter — see
[Engineering decisions](#engineering-decisions--known-limitations).

Run the build script on each architecture you want to support (x86_64,
aarch64) — it packages for whatever architecture it's run on.

### Option C — Manual install (no .deb, any systemd Linux)

```bash
sudo ./scripts/install.sh --enable
```

Same end result as the `.deb`, without needing `dpkg`.

---

## Uninstalling

```bash
# if installed via .deb
sudo apt remove internet-monitor        # keeps data in /var/lib/internet-monitor
sudo apt purge internet-monitor         # also deletes stored history/settings

# if installed via scripts/install.sh
sudo ./scripts/uninstall.sh             # keeps data
sudo ./scripts/uninstall.sh --purge     # also deletes stored history/settings

# AppImage
rm dist/Internet-Monitor-*.AppImage     # it's just a file; nothing else was installed
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

- **`.deb`** (`packaging/deb/`): hand-built via `dpkg-deb` (no `debhelper`)
  from `packaging/deb/debian/{control,postinst,prerm,postrm,conffiles}`.
  `postinst` creates the service user, a venv, and pip-installs the
  backend + CLI from `requirements.txt` — this is why installing the
  package requires network access, and why it's `Architecture: all` (the
  Python dependencies aren't compiled at package-build time).
- **AppImage** (`packaging/appimage/`): an `AppDir` with the app code,
  `pip install --target`-vendored dependencies, `AppRun`, a `.desktop`
  file, and a generated icon, packaged with `appimagetool`
  (`--appimage-extract-and-run`, so it doesn't require FUSE to build).
- **systemd** (`packaging/systemd/internet-monitor.service`): see the
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
- **The AppImage runs on the system Python, not a bundled interpreter.**
  Fully vendoring a relocatable CPython build (e.g. via
  `python-build-standalone`) would make the AppImage larger and more
  complex to maintain across glibc versions for arguably little benefit,
  since virtually every target Linux desktop already has Python 3.10+.
  Only the pure-Python *dependencies* are vendored (via `pip install
  --target`).  A consequence: the AppImage will refuse to run (with a
  clear error) on a system with no `python3` on `PATH` at all, and Python
  C-extension wheels (`pydantic-core`, `uvloop`, etc.) are
  architecture-specific, so `packaging/appimage/build.sh` must be run once
  per target architecture (x86_64, aarch64) rather than cross-built from
  one machine.
- **The "Start on boot" setting never lets the app self-elevate.** It's
  purely a stored preference; actually changing systemd's enabled state is
  a separate, explicit `internet-monitor service enable-boot` command that
  shells out to `sudo systemctl` and will prompt for a password
  interactively. The API/dashboard process itself never gains, requests,
  or needs elevated privileges to do this.
- **`.deb` fetches dependencies from PyPI at install time** rather than
  vendoring wheels, keeping the package itself small and simple
  (`Architecture: all`) at the cost of requiring network access during
  `apt install`. For a fully offline install, use the AppImage (which
  vendors dependencies at *build* time) or `pip download` the
  requirements yourself ahead of time.
- **Desktop notifications use `notify-send`** (a call to the standard
  `libnotify` CLI tool) rather than a Python GUI-toolkit binding, so the
  monitoring service has zero GUI dependencies and runs identically
  headless or on a desktop.
# internet-monitor
