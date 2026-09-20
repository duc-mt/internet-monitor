#!/usr/bin/env bash
# Install Internet Monitor from a source checkout (no .deb/AppImage needed).
# For most users, building the .deb (packaging/deb/build.sh) and installing
# that is easier - this script is the manual equivalent, useful for
# development machines or distros without dpkg.
#
# Usage: sudo ./scripts/install.sh [--enable]
#   --enable   also enable and start the systemd service immediately.
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
  echo "This script must be run as root (try: sudo $0)" >&2
  exit 1
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INSTALL_DIR=/opt/internet-monitor
DATA_DIR=/var/lib/internet-monitor
SERVICE_USER=internet-monitor
SERVICE_FILE=/etc/systemd/system/internet-monitor.service
ENABLE_NOW=false

for arg in "$@"; do
  case "$arg" in
    --enable) ENABLE_NOW=true ;;
    *) echo "Unknown argument: $arg" >&2; exit 1 ;;
  esac
done

echo "==> Checking for required tools"
command -v python3 >/dev/null || { echo "python3 is required" >&2; exit 1; }
PYTHON_VERSION="$(python3 -c 'import sys; print(sys.version_info[:2])')"
echo "    python3 found ($PYTHON_VERSION)"

echo "==> Creating service user/group ($SERVICE_USER)"
if ! id "$SERVICE_USER" >/dev/null 2>&1; then
  useradd --system --no-create-home --shell /usr/sbin/nologin "$SERVICE_USER"
else
  echo "    already exists, skipping"
fi

echo "==> Creating directories"
mkdir -p "$INSTALL_DIR/backend" "$DATA_DIR"
chown -R "$SERVICE_USER:$SERVICE_USER" "$DATA_DIR"

echo "==> Copying backend"
rsync -a --delete "$ROOT_DIR/backend/app" "$INSTALL_DIR/backend/"
cp "$ROOT_DIR/backend/requirements.txt" "$INSTALL_DIR/backend/"

if [[ -d "$ROOT_DIR/frontend/dist" ]]; then
  echo "==> Copying pre-built frontend"
  rsync -a --delete "$ROOT_DIR/frontend/dist" "$INSTALL_DIR/frontend-dist"
  # FastAPI looks for the build two directories up from app/, mirroring the
  # source tree layout (backend/app/../../frontend/dist) - recreate that here.
  mkdir -p "$INSTALL_DIR/frontend"
  rm -rf "$INSTALL_DIR/frontend/dist"
  mv "$INSTALL_DIR/frontend-dist" "$INSTALL_DIR/frontend/dist"
else
  echo "==> No frontend/dist found - run 'npm run build' in frontend/ first if you want the dashboard UI."
  echo "    The API will still work; visit /docs for the interactive API reference."
fi

echo "==> Creating virtual environment"
python3 -m venv "$INSTALL_DIR/venv"
"$INSTALL_DIR/venv/bin/pip" install --upgrade pip -q
"$INSTALL_DIR/venv/bin/pip" install -r "$INSTALL_DIR/backend/requirements.txt" -q
"$INSTALL_DIR/venv/bin/pip" install uvicorn -q
"$INSTALL_DIR/venv/bin/pip" install "$ROOT_DIR/cli" -q

echo "==> Installing CLI wrapper to /usr/local/bin/internet-monitor"
ln -sf "$INSTALL_DIR/venv/bin/internet-monitor" /usr/local/bin/internet-monitor

echo "==> Installing systemd unit"
cp "$ROOT_DIR/packaging/systemd/internet-monitor.service" "$SERVICE_FILE"
systemctl daemon-reload

chown -R "$SERVICE_USER:$SERVICE_USER" "$INSTALL_DIR"

echo
echo "Installed. Next steps:"
echo "  sudo systemctl enable --now internet-monitor    # start now and on every boot"
echo "  sudo systemctl status internet-monitor"
echo "  internet-monitor status"
echo

if [[ "$ENABLE_NOW" == true ]]; then
  echo "==> --enable passed: enabling and starting the service now"
  systemctl enable --now internet-monitor.service
  systemctl status internet-monitor.service --no-pager || true
fi
