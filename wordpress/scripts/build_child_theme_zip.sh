#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
THEME_DIR="$ROOT_DIR/themes/virtualcarhub-motors-child"
PACKAGE_DIR="$ROOT_DIR/packages"
OUTPUT_ZIP="$PACKAGE_DIR/virtualcarhub-motors-child.zip"

mkdir -p "$PACKAGE_DIR"

if ! command -v 7z >/dev/null 2>&1; then
  echo "7z is required to build the zip package."
  exit 1
fi

rm -f "$OUTPUT_ZIP"

(
  cd "$ROOT_DIR/themes"
  7z a -tzip "$OUTPUT_ZIP" "virtualcarhub-motors-child" >/dev/null
)

echo "Built package: $OUTPUT_ZIP"
