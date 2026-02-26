#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PLUGIN_DIR="$ROOT_DIR/plugins/virtualcarhub-motors-sync"
PACKAGE_DIR="$ROOT_DIR/packages"
OUTPUT_ZIP="$PACKAGE_DIR/virtualcarhub-motors-sync.zip"

if [[ ! -d "$PLUGIN_DIR" ]]; then
  echo "Plugin directory not found: $PLUGIN_DIR" >&2
  exit 1
fi

mkdir -p "$PACKAGE_DIR"
rm -f "$OUTPUT_ZIP"

(
  cd "$ROOT_DIR/plugins"
  if command -v 7z >/dev/null 2>&1; then
    7z a -tzip "$OUTPUT_ZIP" "virtualcarhub-motors-sync" >/dev/null
  elif command -v zip >/dev/null 2>&1; then
    zip -rq "$OUTPUT_ZIP" "virtualcarhub-motors-sync"
  else
    echo "Either 7z or zip is required to build package." >&2
    exit 1
  fi
)

echo "Built: $OUTPUT_ZIP"
