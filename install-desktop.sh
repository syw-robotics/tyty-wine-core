#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "$0")" && pwd)
TEMPLATE="$ROOT/tyty-wine.desktop.in"
APPLICATIONS_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
TARGET="$APPLICATIONS_DIR/tyty-wine.desktop"

mkdir -p "$APPLICATIONS_DIR"

# Desktop Exec entries require absolute paths, so render them at install time.
python3 - "$ROOT" "$TEMPLATE" "$TARGET" <<'PY'
import os
import sys

root, template, target = sys.argv[1:]
content = open(template, encoding="utf-8").read().replace("@ROOT@", root)
with open(target, "w", encoding="utf-8") as output:
    output.write(content)
os.chmod(target, 0o644)
PY

if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database "$APPLICATIONS_DIR" >/dev/null 2>&1 || true
fi

echo "Desktop launcher installed: $TARGET"
echo "Search for: Tyty VPN"
