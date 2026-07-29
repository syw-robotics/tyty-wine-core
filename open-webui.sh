#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "$0")" && pwd)
PORTS_FILE="$ROOT/runtime/ports.env"
WEBUI_PORT=29100

"$ROOT/start.sh"
if [[ -f "$PORTS_FILE" ]]; then
  # This generated file contains numeric local ports only.
  source "$PORTS_FILE"
fi

for _ in $(seq 1 150); do
  if (: >/dev/tcp/127.0.0.1/"$WEBUI_PORT") 2>/dev/null; then
    exec xdg-open "http://127.0.0.1:$WEBUI_PORT"
  fi
  sleep 0.1
done

echo "Error: WebUI is unavailable on 127.0.0.1:$WEBUI_PORT" >&2
exit 1
