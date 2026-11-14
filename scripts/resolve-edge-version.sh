#!/usr/bin/env bash
set -euo pipefail
PATH_COMPONENT=${1:?usage: resolve-edge-version.sh <manifest-path>}
MANIFEST=.release-please-manifest.json
[[ -f "$MANIFEST" ]] || { echo "manifest mode is required" >&2; exit 1; }
PR_HEAD=$(gh pr list --state open --label 'autorelease: pending' --json headRefName --limit 1 --jq '.[0].headRefName' 2>/dev/null || true)
PENDING=""
if [[ -n "$PR_HEAD" ]]; then
  PENDING=$(gh api "repos/${GITHUB_REPOSITORY}/contents/${MANIFEST}?ref=${PR_HEAD}" --jq '.content' 2>/dev/null | tr -d '\n' | base64 -d | jq -r --arg path "$PATH_COMPONENT" '.[$path] // empty' || true)
fi
if [[ -n "$PENDING" ]]; then
  BASE=$PENDING
else
  CURRENT=$(jq -r --arg path "$PATH_COMPONENT" '.[$path] // empty' "$MANIFEST")
  [[ -n "$CURRENT" ]] || { echo "no manifest entry for $PATH_COMPONENT" >&2; exit 1; }
  BASE=$(awk -F. '{printf "%d.%d.%d", $1, $2, $3+1}' <<< "$CURRENT")
fi
if [[ "${RAW:-}" == 1 ]]; then
  echo "$BASE"
else
  SHA=${GITHUB_SHA:-$(git rev-parse HEAD)}
  echo "$BASE-${SHA:0:7}"
fi
