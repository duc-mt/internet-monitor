#!/usr/bin/env bash
# test-site.sh — run Internet Monitor as a quick, portable connectivity test
# for a single physical location, with an isolated dataset per site and an
# auto-saved report when you're done.
#
# Save this file at the ROOT of your internet-monitor project (next to
# backend/, frontend/, cli/) and run it from there.
#
# Usage:
#   ./test-site.sh "Client HQ - Floor 3"
#   ./test-site.sh                          # auto-named by timestamp
#
# Each run gets its own SQLite database under ./tmp/<name>/ (inside this
# project, not your home directory) so the gateway target is freshly
# auto-detected for *that* network, and stats never mix between locations.
# ./tmp/ is meant to be git-ignored — see the .gitignore line noted below.
# On Ctrl+C, a CSV + JSON report is saved to that same folder before the
# server stops.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$SCRIPT_DIR/backend"
SITE_NAME="${1:-site-$(date +%Y%m%d-%H%M%S)}"
SAFE_NAME="$(echo "$SITE_NAME" | tr ' /' '--')"
DATA_DIR="$SCRIPT_DIR/tmp/$SAFE_NAME"
PORT="${INTERNET_MONITOR_PORT:-8765}"

if [[ ! -x "$BACKEND_DIR/.venv/bin/python" ]]; then
  echo "No venv found at $BACKEND_DIR/.venv — set that up first (see README)." >&2
  exit 1
fi

mkdir -p "$DATA_DIR"
export INTERNET_MONITOR_DATA_DIR="$DATA_DIR"

echo "==> Testing:  $SITE_NAME"
echo "==> Data dir: $DATA_DIR"

cd "$BACKEND_DIR"
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port "$PORT" &
SERVER_PID=$!

cleanup() {
  echo
  echo "==> Saving report for \"$SITE_NAME\"..."
  curl -s "http://127.0.0.1:$PORT/api/export/measurements.csv" -o "$DATA_DIR/measurements.csv" 2>/dev/null || true
  curl -s "http://127.0.0.1:$PORT/api/export/report.json?range=24h" -o "$DATA_DIR/report.json" 2>/dev/null || true
  kill "$SERVER_PID" 2>/dev/null || true
  wait "$SERVER_PID" 2>/dev/null || true
  echo "    $DATA_DIR/measurements.csv"
  echo "    $DATA_DIR/report.json"
}
trap cleanup EXIT INT TERM

sleep 2
open "http://127.0.0.1:$PORT" 2>/dev/null || true
echo "==> Dashboard open in your browser. Let it run a few minutes, then Ctrl+C to finish and save the report."
wait "$SERVER_PID"
