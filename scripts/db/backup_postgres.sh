#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

OUT_DIR="${1:-$ROOT_DIR/backups/postgres}"
STAMP="$(date -u +"%Y%m%dT%H%M%SZ")"
FILE="$OUT_DIR/virtual_carhub_${STAMP}.dump"

mkdir -p "$OUT_DIR"

docker compose exec -T postgres pg_dump -U vch -d virtual_carhub -Fc >"$FILE"
echo "Backup written: $FILE"
