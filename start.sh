#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "$0")" && pwd)
RUNTIME_DIR="$ROOT/runtime"
PREFIX="$RUNTIME_DIR/wine-prefix"
WORK_DIR="$RUNTIME_DIR/work"
PID_FILE="$RUNTIME_DIR/mihomo.pid"
LOG_FILE="$RUNTIME_DIR/mihomo.log"
WEB_PID_FILE="$RUNTIME_DIR/webui.pid"
WEB_LOG_FILE="$RUNTIME_DIR/webui.log"
INDICATOR_PID_FILE="$RUNTIME_DIR/indicator.pid"
INDICATOR_LOG_FILE="$RUNTIME_DIR/indicator.log"
LOCK_FILE="$RUNTIME_DIR/start.lock"
PORTS_FILE="$RUNTIME_DIR/ports.env"
ACTIVE_CONFIG="$RUNTIME_DIR/active-config.yaml"
WINE=/usr/lib/wine/wine64
WINESERVER=/usr/lib/wine/wineserver
MIXED_PORT=29674
CONTROLLER_PORT=29090
WEBUI_PORT=29100

mkdir -p "$PREFIX" "$WORK_DIR"
if [[ -f "$PORTS_FILE" ]]; then
  # This file is generated below and contains numeric local ports only.
  source "$PORTS_FILE"
fi
exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  echo "Tyty is already starting; please wait"
  exit 0
fi

pid_matches() {
  local file=$1 expected=$2 pid cmdline
  [[ -s "$file" ]] || return 1
  pid=$(cat "$file")
  [[ "$pid" =~ ^[0-9]+$ ]] && kill -0 "$pid" 2>/dev/null || return 1
  cmdline=$(tr '\0' ' ' <"/proc/$pid/cmdline" 2>/dev/null || true)
  [[ "$cmdline" == *"$expected"* ]]
}

port_open() {
  (: >/dev/tcp/127.0.0.1/"$1") 2>/dev/null
}

core_ready() {
  port_open "$MIXED_PORT" && curl -fsS --max-time 1 \
    "http://127.0.0.1:$CONTROLLER_PORT/version" >/dev/null 2>&1
}

write_ports() {
  printf 'MIXED_PORT=%s\nCONTROLLER_PORT=%s\nWEBUI_PORT=%s\n' \
    "$MIXED_PORT" "$CONTROLLER_PORT" "$WEBUI_PORT" >"$PORTS_FILE"
}

build_active_config() {
  python3 - "$ROOT/config.yaml" "$ACTIVE_CONFIG" "$MIXED_PORT" "$CONTROLLER_PORT" <<'PY'
import os
import sys

import yaml

source, target, mixed_port, controller_port = sys.argv[1:]
with open(source, encoding="utf-8") as stream:
    config = yaml.safe_load(stream) or {}
config["mixed-port"] = int(mixed_port)
config["external-controller"] = f"127.0.0.1:{controller_port}"
with open(target, "w", encoding="utf-8") as stream:
    yaml.safe_dump(config, stream, allow_unicode=True, sort_keys=False)
os.chmod(target, 0o600)
PY
}

stop_prefix() {
  WINEPREFIX="$PREFIX" "$WINESERVER" -k 2>/dev/null || true
  timeout 3s env WINEPREFIX="$PREFIX" "$WINESERVER" -w 2>/dev/null || true
  # Wine can briefly retain Windows sockets after wineserver exits.
  sleep 0.5
}

find_service_pid() {
  pgrep -u "$(id -u)" -f "$1" | head -n 1 || true
}

enable_system_proxy() {
  if ! command -v gsettings >/dev/null 2>&1; then
    echo "Warning: gsettings is unavailable; configure the system proxy manually" >&2
    return
  fi
  gsettings set org.gnome.system.proxy.http host '127.0.0.1'
  gsettings set org.gnome.system.proxy.http port "$MIXED_PORT"
  gsettings set org.gnome.system.proxy.https host '127.0.0.1'
  gsettings set org.gnome.system.proxy.https port "$MIXED_PORT"
  gsettings set org.gnome.system.proxy.socks host '127.0.0.1'
  gsettings set org.gnome.system.proxy.socks port "$MIXED_PORT"
  gsettings set org.gnome.system.proxy mode 'manual'
  echo "Ubuntu system proxy enabled"
}

start_webui() {
  if pid_matches "$WEB_PID_FILE" "$ROOT/webui.js" && port_open "$WEBUI_PORT"; then
    return
  fi
  local existing
  existing=$(find_service_pid "^node $ROOT/webui.js$")
  if [[ -n "$existing" ]] && port_open "$WEBUI_PORT"; then
    echo "$existing" >"$WEB_PID_FILE"
    return
  fi
  rm -f "$WEB_PID_FILE"
  CORE_PORT="$CONTROLLER_PORT" WEBUI_PORT="$WEBUI_PORT" \
    nohup node "$ROOT/webui.js" 9>&- >"$WEB_LOG_FILE" 2>&1 &
  echo $! >"$WEB_PID_FILE"
}

start_indicator() {
  if pid_matches "$INDICATOR_PID_FILE" "$ROOT/indicator.py"; then
    return
  fi
  local existing
  existing=$(find_service_pid "^python3 $ROOT/indicator.py$")
  if [[ -n "$existing" ]]; then
    echo "$existing" >"$INDICATOR_PID_FILE"
    return
  fi
  rm -f "$INDICATOR_PID_FILE"
  MIXED_PORT="$MIXED_PORT" CONTROLLER_PORT="$CONTROLLER_PORT" WEBUI_PORT="$WEBUI_PORT" \
    nohup python3 "$ROOT/indicator.py" 9>&- >"$INDICATOR_LOG_FILE" 2>&1 &
  echo $! >"$INDICATOR_PID_FILE"
}

finish_start() {
  # Keep the preferred node when it exists; otherwise retain the profile default.
  curl -fsS --max-time 2 -X PUT -H 'Content-Type: application/json' \
    -d '{"name":"新加坡02_NF/GPT"}' \
    "http://127.0.0.1:$CONTROLLER_PORT/proxies/Tyty" >/dev/null || \
    echo "Warning: preferred node is unavailable; using the profile default" >&2
  start_webui
  start_indicator
  enable_system_proxy
  echo "HTTP/SOCKS: 127.0.0.1:$MIXED_PORT"
  echo "WebUI: http://127.0.0.1:$WEBUI_PORT"
}

# Trust live services rather than a PID file, because Wine may replace its launcher process.
if core_ready; then
  echo "Tyty Wine core is already running"
  finish_start
  exit 0
fi

rm -f "$PID_FILE"
# A dead core makes existing helpers stale, especially if the fallback ports change.
pkill -u "$(id -u)" -f "^node $ROOT/webui.js$" 2>/dev/null || true
pkill -u "$(id -u)" -f "^python3 $ROOT/indicator.py$" 2>/dev/null || true
rm -f "$WEB_PID_FILE" "$INDICATOR_PID_FILE"
stop_prefix

port_pairs=("29674:29090" "29675:29091" "29676:29092")
for pair in "${port_pairs[@]}"; do
  MIXED_PORT=${pair%%:*}
  CONTROLLER_PORT=${pair##*:}
  write_ports
  build_active_config
  : >"$LOG_FILE"
  wine_root="Z:$ROOT"
  WINEPREFIX="$PREFIX" WINEDEBUG=-all nohup "$WINE" "$ROOT/mihomo.exe" \
    -d "$wine_root/runtime/work" -f "$wine_root/runtime/active-config.yaml" \
    9>&- >"$LOG_FILE" 2>&1 &
  pid=$!
  echo "$pid" >"$PID_FILE"

  for _ in $(seq 1 30); do
    if core_ready; then
      echo "Tyty Wine core started (PID $pid)"
      finish_start
      exit 0
    fi
    if ! kill -0 "$pid" 2>/dev/null; then
      break
    fi
    sleep 0.2
  done

  echo "Ports $MIXED_PORT/$CONTROLLER_PORT failed; trying the next pair" >&2
  stop_prefix
  rm -f "$PID_FILE"
done

if command -v gsettings >/dev/null 2>&1; then
  gsettings set org.gnome.system.proxy mode 'none'
fi
echo "Tyty Wine core failed on all local port pairs; see $LOG_FILE" >&2
exit 1
