#!/usr/bin/env bash
# Uninstall Internet Monitor (the manual/source install, see install.sh).
#
# Usage: sudo ./scripts/uninstall.sh [--purge]
#   --purge   also delete /var/lib/internet-monitor (all measurement history
#             and settings). Without this flag, data is left in place in
#             case you reinstall later.
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
  echo "This script must be run as root (try: sudo $0)" >&2
  exit 1
fi

INSTALL_DIR=/opt/internet-monitor
DATA_DIR=/var/lib/internet-monitor
SERVICE_USER=internet-monitor
SERVICE_FILE=/etc/systemd/system/internet-monitor.service
PURGE=false

for arg in "$@"; do
  case "$arg" in
    --purge) PURGE=true ;;
    *) echo "Unknown argument: $arg" >&2; exit 1 ;;
  esac
done

echo "==> Stopping and disabling service"
systemctl stop internet-monitor.service 2>/dev/null || true
systemctl disable internet-monitor.service 2>/dev/null || true

echo "==> Removing systemd unit"
rm -f "$SERVICE_FILE"
systemctl daemon-reload

echo "==> Removing CLI wrapper"
rm -f /usr/local/bin/internet-monitor

echo "==> Removing installed files"
rm -rf "$INSTALL_DIR"

if [[ "$PURGE" == true ]]; then
  echo "==> --purge passed: removing $DATA_DIR (all history and settings)"
  rm -rf "$DATA_DIR"
else
  echo "==> Leaving $DATA_DIR in place (pass --purge to remove it too)"
fi

echo "==> Removing service user/group"
if id "$SERVICE_USER" >/dev/null 2>&1; then
  userdel "$SERVICE_USER" 2>/dev/null || true
fi

echo "Uninstalled."
