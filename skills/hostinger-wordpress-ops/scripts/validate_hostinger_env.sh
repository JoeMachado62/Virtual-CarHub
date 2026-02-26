#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
TOOL_ROOT="${HOSTINGER_TOOL_ROOT:-$HOME/.cache/hostinger-tools}"

echo "Skill root: $SKILL_ROOT"
echo "Tool root:  $TOOL_ROOT"
echo

require_cmd() {
  local cmd="$1"
  if command -v "$cmd" >/dev/null 2>&1; then
    echo "[OK] command found: $cmd"
  else
    echo "[WARN] command missing: $cmd"
  fi
}

require_cmd git
require_cmd node
require_cmd npm
require_cmd python3
echo

token="${HOSTINGER_API_TOKEN:-${HOSTINGER_TOKEN:-${H_PANEL_API_TOKEN:-${HOSTINGER_ACCESS_TOKEN:-${HAPI_API_TOKEN:-}}}}}"
if [[ -n "$token" ]]; then
  echo "[OK] Hostinger token detected in environment"
else
  echo "[WARN] No Hostinger token found (set HOSTINGER_API_TOKEN, HOSTINGER_TOKEN, or HAPI_API_TOKEN)"
  echo "[INFO] Tip: put token export in ~/.profile or ~/.bash_profile (not only ~/.bashrc) for non-interactive shells."
fi
echo

check_repo() {
  local repo_dir="$1"
  local label="$2"
  if [[ -d "$repo_dir/.git" ]]; then
    echo "[OK] repo present: $label ($repo_dir)"
  else
    echo "[WARN] repo missing: $label ($repo_dir)"
  fi
}

check_repo "$TOOL_ROOT/api-cli" "hostinger/api-cli"
check_repo "$TOOL_ROOT/api-mcp-server" "hostinger/api-mcp-server"
check_repo "$TOOL_ROOT/api" "hostinger/api"
echo

echo "Validation completed."
