#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

if git remote get-url origin >/dev/null 2>&1; then
  git fetch --prune origin
  git checkout main
  git pull --ff-only origin main
else
  echo "No git remote configured yet. Skipping fetch/pull."
fi

docker compose up -d --build backend frontend
docker compose ps
