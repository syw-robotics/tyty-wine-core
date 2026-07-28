#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "$0")" && pwd)
RUNTIME_DIR="$ROOT/runtime"
PREFIX="$RUNTIME_DIR/wine-prefix"
PID_FILE="$RUNTIME_DIR/mihomo.pid"
WEB_PID_FILE="$RUNTIME_DIR/webui.pid"
INDICATOR_PID_FILE="$RUNTIME_DIR/indicator.pid"
MIXED_PORT=29674
if [[ -f "$RUNTIME_DIR/ports.env" ]]; then
  source "$RUNTIME_DIR/ports.env"
fi

stop_service() {
  local pid_file=$1 pattern=$2 pid
  # Also stop an orphaned instance whose PID file was lost or stale.
  while read -r pid; do
    [[ -n "$pid" ]] && kill "$pid" 2>/dev/null || true
  done < <(pgrep -u "$(id -u)" -f "$pattern" || true)
  rm -f "$pid_file"
}

# Disable the desktop proxy before stopping the local listener.
if command -v gsettings >/dev/null 2>&1; then
  gsettings set org.gnome.system.proxy mode 'none'
  echo "Ubuntu system proxy disabled"
fi

stop_service "$WEB_PID_FILE" "^node $ROOT/webui.js$"
stop_service "$INDICATOR_PID_FILE" "^python3 $ROOT/indicator.py$"

if [[ -f "$PID_FILE" ]]; then
  pid=$(cat "$PID_FILE")
  kill "$pid" 2>/dev/null || true
  rm -f "$PID_FILE"
fi

WINEPREFIX="$PREFIX" /usr/lib/wine/wineserver -k 2>/dev/null || true
timeout 3s env WINEPREFIX="$PREFIX" /usr/lib/wine/wineserver -w 2>/dev/null || true

for _ in $(seq 1 20); do
  if ! (: >/dev/tcp/127.0.0.1/"$MIXED_PORT") 2>/dev/null; then
    break
  fi
  sleep 0.25
done
echo "Tyty Wine core, WebUI, and Indicator stopped"
