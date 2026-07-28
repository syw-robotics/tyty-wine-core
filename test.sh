#!/usr/bin/env bash
set -euo pipefail

# Test the same mixed proxy endpoint configured in GNOME Settings.
ROOT=$(cd "$(dirname "$0")" && pwd)
MIXED_PORT=29674
if [[ -f "$ROOT/runtime/ports.env" ]]; then
  source "$ROOT/runtime/ports.env"
fi
curl -fsS -o /dev/null \
  --max-time 20 \
  --proxy "http://127.0.0.1:$MIXED_PORT" \
  https://www.google.com/generate_204
echo "Tyty Wine proxy is working"
