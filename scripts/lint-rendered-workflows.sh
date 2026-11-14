#!/usr/bin/env bash
set -euo pipefail
ROOT=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --root) ROOT=$2; shift 2 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done
[[ -d "$ROOT/.github/workflows" ]] || { echo "rendered workflow directory is missing" >&2; exit 2; }
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT
shopt -s nullglob
templates=("$ROOT"/.github/workflows/*.yml.template "$ROOT"/.github/workflows/*.yaml.template)
[[ ${#templates[@]} -gt 0 ]] || { echo "no rendered consumer workflow templates found" >&2; exit 2; }
for source in "${templates[@]}"; do
  name=$(basename "$source")
  cp "$source" "$WORK/${name%.template}"
done
actionlint "$WORK"/*.yml "$WORK"/*.yaml
echo "actionlint passed for ${#templates[@]} rendered consumer workflows"
