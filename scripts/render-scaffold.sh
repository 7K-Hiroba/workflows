#!/usr/bin/env bash
set -euo pipefail

SOURCE="$(cd "$(dirname "$0")/.." && pwd)/scaffold"
OUT=""
SHA=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --source) SOURCE=$2; shift 2 ;;
    --out) OUT=$2; shift 2 ;;
    --sha) SHA=$2; shift 2 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done
[[ -d "$SOURCE" ]] || { echo "source is not a directory: $SOURCE" >&2; exit 2; }
[[ -n "$OUT" ]] || { echo "--out is required" >&2; exit 2; }
[[ "$SHA" =~ ^[0-9a-fA-F]{40}$ ]] || { echo "--sha must be a full 40-character commit SHA" >&2; exit 2; }
if [[ -d "$OUT" ]] && [[ -n "$(find "$OUT" -mindepth 1 -print -quit)" ]]; then
  echo "refusing to overwrite non-empty output: $OUT" >&2
  exit 2
fi
mkdir -p "$OUT"
tar -C "$SOURCE" \
  --exclude='.git' --exclude='.venv' --exclude='node_modules' --exclude='dist' \
  --exclude='*.log' --exclude='*.pyc' --exclude='__pycache__' -cf - . | tar -C "$OUT" -xf -
grep -RIlZ '__WORKFLOWS_V1_SHA__' "$OUT" | xargs -0 -r sed -i "s/__WORKFLOWS_V1_SHA__/$SHA/g"
if grep -R -l '__WORKFLOWS_V1_SHA__' "$OUT" >/dev/null 2>&1; then
  echo "unresolved workflow SHA placeholder remains" >&2
  exit 1
fi
echo "rendered $SOURCE to $OUT with workflow SHA $SHA"
