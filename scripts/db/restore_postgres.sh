#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: bash scripts/db/restore_postgres.sh <backup_file.dump>"
  exit 1
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

BACKUP_FILE="$1"
if [[ ! -f "$BACKUP_FILE" ]]; then
  echo "Backup file not found: $BACKUP_FILE"
  exit 1
fi

echo "Restoring from: $BACKUP_FILE"
docker compose exec -T postgres psql -U vch -d postgres -c "DROP DATABASE IF EXISTS virtual_carhub;"
docker compose exec -T postgres psql -U vch -d postgres -c "CREATE DATABASE virtual_carhub;"
cat "$BACKUP_FILE" | docker compose exec -T postgres pg_restore -U vch -d virtual_carhub --no-owner --clean --if-exists
echo "Restore completed."
