#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "$0")" && pwd)
SOURCE=${1:-"$ROOT/windows-export/config.yaml"}
TARGET="$ROOT/config.yaml"
RUNTIME_DIR="$ROOT/runtime"
PREFIX="$RUNTIME_DIR/wine-prefix"
TEST_DIR="$RUNTIME_DIR/update-test"
TEMP_CONFIG=$(mktemp "$RUNTIME_DIR/config.XXXXXX.yaml")
WINE=/usr/lib/wine/wine64

cleanup() {
  rm -f "$TEMP_CONFIG"
}
trap cleanup EXIT

if [[ ! -f "$SOURCE" ]]; then
  echo "Windows Tyty config not found: $SOURCE" >&2
  exit 1
fi

mkdir -p "$RUNTIME_DIR" "$PREFIX" "$TEST_DIR"

# Windows Tyty stores the runtime YAML as Base64 after repeating-key XOR.
python3 - "$SOURCE" "$TEMP_CONFIG" <<'PY'
import base64
import os
import sys

import yaml

source, target = sys.argv[1:]
key = b"SIzLm51puIlCewdfDWCgWXQ_Kq-ST242UBEVBhKReO7guLPFH0="
ciphertext = base64.b64decode(open(source, "rb").read().strip(), validate=True)
plaintext = bytes(value ^ key[index % len(key)] for index, value in enumerate(ciphertext))
config = yaml.safe_load(plaintext) or {}

# Keep the Windows node definitions while adapting listeners for Ubuntu/Wine.
config["allow-lan"] = False
config["bind-address"] = "127.0.0.1"
config["mixed-port"] = 29674
config["port"] = 0
config["socks-port"] = 0
config["redir-port"] = 0
config["tproxy-port"] = 0
config["external-controller"] = "127.0.0.1:29090"
config["rules"] = ["MATCH,Tyty"]
config["geodata-mode"] = True

config.setdefault("tun", {})["enable"] = False
fallback_filter = config.setdefault("dns", {}).setdefault("fallback-filter", {})
fallback_filter["geoip"] = False

with open(target, "w", encoding="utf-8") as output:
    yaml.safe_dump(config, output, allow_unicode=True, sort_keys=False)
os.chmod(target, 0o600)
PY

# Validate before replacing the known-good local configuration.
wine_test_dir="Z:$TEST_DIR"
wine_temp_config="Z:$TEMP_CONFIG"
WINEPREFIX="$PREFIX" WINEDEBUG=-all "$WINE" "$ROOT/mihomo.exe" \
  -d "$wine_test_dir" -t -f "$wine_temp_config"

was_running=false
if [[ -f "$RUNTIME_DIR/mihomo.pid" ]] && kill -0 "$(cat "$RUNTIME_DIR/mihomo.pid")" 2>/dev/null; then
  was_running=true
fi

if [[ -f "$TARGET" ]]; then
  cp "$TARGET" "$RUNTIME_DIR/config.backup.yaml"
  chmod 600 "$RUNTIME_DIR/config.backup.yaml"
fi
mv "$TEMP_CONFIG" "$TARGET"
chmod 600 "$TARGET"

if [[ "$was_running" == true ]]; then
  "$ROOT/stop.sh"
  "$ROOT/start.sh"
fi

echo "Tyty configuration updated from: $SOURCE"
