#!/usr/bin/env bash
set -euo pipefail

if [[ "${1:-}" != "--" ]]; then
  echo "Usage: $0 -- <command ...>"
  exit 1
fi
shift

if [[ "$#" -eq 0 ]]; then
  echo "No command provided."
  exit 1
fi

cmd=("$@")
cmd_text="$(printf ' %q' "${cmd[@]}")"

is_mutating=0
for token in "${cmd[@]}"; do
  case "${token,,}" in
    create|update|delete|remove|destroy|attach|detach|reset|rotate|change|set|patch|post|put)
      is_mutating=1
      break
      ;;
  esac
done

echo "[INFO] Command:$cmd_text"

if [[ "$is_mutating" -eq 1 ]]; then
  if [[ "${HOSTINGER_ALLOW_WRITE:-0}" != "1" ]]; then
    echo "[BLOCKED] Mutating command detected."
    echo "Set HOSTINGER_ALLOW_WRITE=1 to proceed intentionally."
    exit 2
  fi
  echo "[WARN] Mutating operation allowed by HOSTINGER_ALLOW_WRITE=1"
else
  echo "[OK] Read-only style command detected"
fi

"${cmd[@]}"
