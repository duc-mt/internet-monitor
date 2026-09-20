#!/usr/bin/env bash
# Build internet-monitor.deb from this source tree.
#
# Usage: ./packaging/deb/build.sh [output-dir]
#
# Requires: dpkg-deb (part of dpkg, present on any Debian/Ubuntu system).
# If frontend/dist doesn't exist yet, this script builds it first (requires
# node/npm) - or you can build it yourself and re-run this script to skip
# that step.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PKG_NAME=internet-monitor
VERSION=1.0.0
ARCH=all
OUT_DIR="${1:-$ROOT_DIR/dist}"
STAGE_DIR="$ROOT_DIR/packaging/deb/build/${PKG_NAME}_${VERSION}_${ARCH}"

command -v dpkg-deb >/dev/null || { echo "dpkg-deb is required (install the 'dpkg' package)." >&2; exit 1; }

if [[ ! -d "$ROOT_DIR/frontend/dist" ]]; then
  echo "==> frontend/dist not found - building it now"
  if command -v npm >/dev/null; then
    (cd "$ROOT_DIR/frontend" && npm install && npm run build)
  else
    echo "npm not found. Build the frontend manually (cd frontend && npm install && npm run build)" >&2
    echo "and re-run this script, or continue without a dashboard UI (API-only)." >&2
    read -r -p "Continue without a built frontend? [y/N] " ans
    [[ "$ans" == "y" || "$ans" == "Y" ]] || exit 1
  fi
fi

echo "==> Staging package tree"
rm -rf "$STAGE_DIR"
mkdir -p "$STAGE_DIR/DEBIAN"
mkdir -p "$STAGE_DIR/opt/internet-monitor/backend"
mkdir -p "$STAGE_DIR/etc/systemd/system"

cp "$ROOT_DIR"/packaging/deb/debian/control "$STAGE_DIR/DEBIAN/control"
cp "$ROOT_DIR"/packaging/deb/debian/conffiles "$STAGE_DIR/DEBIAN/conffiles"
cp "$ROOT_DIR"/packaging/deb/debian/postinst "$STAGE_DIR/DEBIAN/postinst"
cp "$ROOT_DIR"/packaging/deb/debian/prerm "$STAGE_DIR/DEBIAN/prerm"
cp "$ROOT_DIR"/packaging/deb/debian/postrm "$STAGE_DIR/DEBIAN/postrm"
chmod 755 "$STAGE_DIR"/DEBIAN/postinst "$STAGE_DIR"/DEBIAN/prerm "$STAGE_DIR"/DEBIAN/postrm

# Installed-Size (KB) - dpkg-deb wants this in the control file for a tidy package.
SIZE_KB=$(du -sk "$ROOT_DIR/backend/app" | cut -f1)
echo "Installed-Size: $SIZE_KB" >> "$STAGE_DIR/DEBIAN/control"

cp -r "$ROOT_DIR/backend/app" "$STAGE_DIR/opt/internet-monitor/backend/"
cp "$ROOT_DIR/backend/requirements.txt" "$STAGE_DIR/opt/internet-monitor/backend/"
find "$STAGE_DIR/opt/internet-monitor/backend/app" -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true

cp -r "$ROOT_DIR/cli" "$STAGE_DIR/opt/internet-monitor/cli-src"
rm -rf "$STAGE_DIR/opt/internet-monitor/cli-src/internet_monitor_cli.egg-info"
find "$STAGE_DIR/opt/internet-monitor/cli-src" -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true

if [[ -d "$ROOT_DIR/frontend/dist" ]]; then
  mkdir -p "$STAGE_DIR/opt/internet-monitor/frontend"
  cp -r "$ROOT_DIR/frontend/dist" "$STAGE_DIR/opt/internet-monitor/frontend/dist"
fi

cp "$ROOT_DIR/packaging/systemd/internet-monitor.service" "$STAGE_DIR/etc/systemd/system/internet-monitor.service"

echo "==> Building .deb"
mkdir -p "$OUT_DIR"
dpkg-deb --root-owner-group --build "$STAGE_DIR" "$OUT_DIR/${PKG_NAME}_${VERSION}_${ARCH}.deb"

echo
echo "Built: $OUT_DIR/${PKG_NAME}_${VERSION}_${ARCH}.deb"
echo "Install with: sudo apt install $OUT_DIR/${PKG_NAME}_${VERSION}_${ARCH}.deb"
echo "(or: sudo dpkg -i $OUT_DIR/${PKG_NAME}_${VERSION}_${ARCH}.deb && sudo apt -f install)"
