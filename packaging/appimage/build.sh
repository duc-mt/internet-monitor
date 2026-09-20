#!/usr/bin/env bash
# Build an Internet Monitor AppImage - a portable, no-install way to run
# the app (as an alternative to the .deb/systemd install).
#
# This bundles the app's pure-Python dependencies but runs them with the
# *system* python3 (>=3.10) rather than a fully embedded interpreter - see
# AppRun and the README for why. It builds an AppImage for whatever
# architecture this script runs on (x86_64 or aarch64); to produce both,
# run this script once on each architecture.
#
# Usage: ./packaging/appimage/build.sh [output-dir]
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PKG_DIR="$ROOT_DIR/packaging/appimage"
BUILD_DIR="$PKG_DIR/build"
APPDIR="$BUILD_DIR/AppDir"
OUT_DIR="${1:-$ROOT_DIR/dist}"
ARCH="$(uname -m)"

command -v python3 >/dev/null || { echo "python3 is required" >&2; exit 1; }

if [[ ! -d "$ROOT_DIR/frontend/dist" ]]; then
  echo "==> frontend/dist not found - building it now"
  if command -v npm >/dev/null; then
    (cd "$ROOT_DIR/frontend" && npm install && npm run build)
  else
    echo "npm not found; the AppImage will run API-only without a dashboard UI." >&2
  fi
fi

echo "==> Staging AppDir"
rm -rf "$BUILD_DIR"
mkdir -p "$APPDIR/opt/internet-monitor/backend"
mkdir -p "$APPDIR/usr/lib/internet-monitor-deps"

cp -r "$ROOT_DIR/backend/app" "$APPDIR/opt/internet-monitor/backend/"
find "$APPDIR/opt/internet-monitor/backend/app" -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true

if [[ -d "$ROOT_DIR/frontend/dist" ]]; then
  mkdir -p "$APPDIR/opt/internet-monitor/frontend"
  cp -r "$ROOT_DIR/frontend/dist" "$APPDIR/opt/internet-monitor/frontend/dist"
fi

echo "==> Vendoring Python dependencies for $ARCH (pip install --target)"
python3 -m pip install --target "$APPDIR/usr/lib/internet-monitor-deps" --quiet \
  -r "$ROOT_DIR/backend/requirements.txt" \
  uvicorn \
  "$ROOT_DIR/cli"
find "$APPDIR/usr/lib/internet-monitor-deps" -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true

cp "$PKG_DIR/AppRun" "$APPDIR/AppRun"
chmod +x "$APPDIR/AppRun"
cp "$PKG_DIR/internet-monitor.desktop" "$APPDIR/internet-monitor.desktop"
cp "$PKG_DIR/internet-monitor.png" "$APPDIR/internet-monitor.png"
# appimagetool also looks for a top-level .DirIcon
cp "$PKG_DIR/internet-monitor.png" "$APPDIR/.DirIcon"

echo "==> Locating appimagetool"
APPIMAGETOOL="$BUILD_DIR/appimagetool-$ARCH.AppImage"
if [[ ! -x "$APPIMAGETOOL" ]]; then
  URL="https://github.com/AppImage/AppImageKit/releases/download/continuous/appimagetool-${ARCH}.AppImage"
  echo "    downloading $URL"
  if command -v curl >/dev/null; then
    curl -fL "$URL" -o "$APPIMAGETOOL"
  else
    wget -O "$APPIMAGETOOL" "$URL"
  fi
  chmod +x "$APPIMAGETOOL"
fi

echo "==> Building AppImage"
mkdir -p "$OUT_DIR"
# --appimage-extract-and-run avoids needing FUSE, which is often unavailable
# inside containers/CI.
ARCH="$ARCH" "$APPIMAGETOOL" --appimage-extract-and-run "$APPDIR" \
  "$OUT_DIR/Internet-Monitor-${ARCH}.AppImage"

chmod +x "$OUT_DIR/Internet-Monitor-${ARCH}.AppImage"
echo
echo "Built: $OUT_DIR/Internet-Monitor-${ARCH}.AppImage"
echo "Run it directly: $OUT_DIR/Internet-Monitor-${ARCH}.AppImage"
echo "Or use the CLI without installing: $OUT_DIR/Internet-Monitor-${ARCH}.AppImage --cli status"
