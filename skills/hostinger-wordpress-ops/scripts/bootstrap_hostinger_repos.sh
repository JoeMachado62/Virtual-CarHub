#!/usr/bin/env bash
set -euo pipefail

TOOL_ROOT="${HOSTINGER_TOOL_ROOT:-$HOME/.cache/hostinger-tools}"
mkdir -p "$TOOL_ROOT"

sync_repo() {
  local name="$1"
  local url="$2"
  local path="$TOOL_ROOT/$name"

  if [[ -d "$path/.git" ]]; then
    echo "[INFO] Updating $name"
    git -C "$path" pull --ff-only
  else
    echo "[INFO] Cloning $name"
    git clone "$url" "$path"
  fi
}

sync_repo "api-cli" "https://github.com/hostinger/api-cli.git"
sync_repo "api-mcp-server" "https://github.com/hostinger/api-mcp-server.git"
sync_repo "api" "https://github.com/hostinger/api.git"

echo
echo "[OK] Hostinger repositories ready in $TOOL_ROOT"
