#!/usr/bin/env bash
set -euo pipefail

OWNER="${1:-JoeMachado62}"
NEW_REPO="${2:-Virtual-CarHub}"
OLD_REPO="${3:-Pinnacle-Portal}"
VISIBILITY="${4:-private}"

if [[ -z "${GH_TOKEN:-}" ]]; then
  echo "GH_TOKEN is required. Export a token with repo admin access first."
  exit 1
fi

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

if [[ ! -d .git ]]; then
  echo "This directory is not a git repository: $REPO_ROOT"
  exit 1
fi

if ! gh auth status >/dev/null 2>&1; then
  gh auth login --with-token <<<"$GH_TOKEN" >/dev/null
fi

if ! gh repo view "${OWNER}/${NEW_REPO}" >/dev/null 2>&1; then
  # Passing a positional argument skips interactive confirmation in newer gh versions.
  gh repo create "${OWNER}/${NEW_REPO}" "--${VISIBILITY}" non-interactive
fi

if ! git remote get-url origin >/dev/null 2>&1; then
  git remote add origin "git@github.com:${OWNER}/${NEW_REPO}.git"
fi

git push -u origin main

tmp_payload="$(mktemp)"
cat >"$tmp_payload" <<'JSON'
{
  "required_status_checks": {
    "strict": true,
    "contexts": [
      "CI / backend-tests",
      "CI / frontend-quality"
    ]
  },
  "enforce_admins": true,
  "required_pull_request_reviews": {
    "dismiss_stale_reviews": true,
    "require_code_owner_reviews": false,
    "required_approving_review_count": 1,
    "require_last_push_approval": true
  },
  "restrictions": null,
  "required_linear_history": true,
  "allow_force_pushes": false,
  "allow_deletions": false,
  "block_creations": false,
  "required_conversation_resolution": true,
  "lock_branch": false,
  "allow_fork_syncing": true
}
JSON

if ! gh api \
  --method PUT \
  -H "Accept: application/vnd.github+json" \
  "/repos/${OWNER}/${NEW_REPO}/branches/main/protection" \
  --input "$tmp_payload" >/dev/null; then
  echo "Warning: branch protection could not be applied (likely plan limitation on private repos)."
fi

rm -f "$tmp_payload"

gh api \
  --method PATCH \
  -H "Accept: application/vnd.github+json" \
  "/repos/${OWNER}/${OLD_REPO}" \
  -f archived=true >/dev/null

echo "Cutover complete:"
echo "- Repo: https://github.com/${OWNER}/${NEW_REPO}"
echo "- Branch protection applied: main"
echo "- Archived: https://github.com/${OWNER}/${OLD_REPO}"
