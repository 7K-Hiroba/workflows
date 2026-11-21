#!/usr/bin/env bash
set -euo pipefail
ROOT=""
PLAN=""
SOURCE_SHA=""
EVIDENCE=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --root) ROOT=$2; shift 2 ;;
    --plan) PLAN=$2; shift 2 ;;
    --source-sha) SOURCE_SHA=$2; shift 2 ;;
    --evidence) EVIDENCE=$2; shift 2 ;;
    *) echo "unknown argument $1" >&2; exit 2 ;;
  esac
done
[[ -d "$ROOT" && -f "$PLAN" && -d "$EVIDENCE" && "$SOURCE_SHA" =~ ^[0-9a-fA-F]{40}$ ]] || { echo "invalid finalization arguments" >&2; exit 2; }
SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
export PLAN EVIDENCE SOURCE_SHA SCRIPT_DIR
python3 - <<'PY'
import json, os, sys
from pathlib import Path
sys.path.insert(0, os.environ["SCRIPT_DIR"])
from lib.release_contract import contract, validate_artifact
plan = json.load(open(os.environ["PLAN"]))
evidence = Path(os.environ["EVIDENCE"])
source = os.environ["SOURCE_SHA"].lower()
for component in plan["components"]:
    expected = contract(component, plan["app"], plan["registryPrefix"], source, "normal")
    filename = f"artifact-{expected['key']}.json"
    path = evidence / filename
    if not path.is_file():
        raise SystemExit(f"missing verified artifact evidence for {component['kind']}/{component['name']}: {filename}")
    data = json.load(open(path))
    validate_artifact(data, component, plan["app"], plan["registryPrefix"], source, "normal")
PY
mapfile -t COMPONENTS < <(jq -r '.components[] | select(.kind != "smoke" or .fixtureOnly == true) | [.kind,(.releaseComponent // .name),.path,.version] | @tsv' "$PLAN")
[[ ${#COMPONENTS[@]} -gt 0 ]] || { echo "no components to finalize" >&2; exit 2; }
git -C "$ROOT" config gpg.format x509
git -C "$ROOT" config gpg.x509.program gitsign
git -C "$ROOT" config gitsign.tokenProvider github-actions
TAGS=()
for row in "${COMPONENTS[@]}"; do
  IFS=$'\t' read -r _ NAME _ VERSION <<< "$row"
  TAG="$NAME-v$VERSION"
  EXISTING=$(git -C "$ROOT" rev-parse -q --verify "refs/tags/$TAG^{commit}" 2>/dev/null || true)
  if [[ -n "$EXISTING" ]]; then
    [[ "$EXISTING" == "$SOURCE_SHA" ]] || { echo "tag $TAG points at $EXISTING, not $SOURCE_SHA" >&2; exit 1; }
  else
    git -C "$ROOT" tag -s -a "$TAG" -m "Release $TAG" "$SOURCE_SHA"
  fi
  gitsign verify --certificate-oidc-issuer https://token.actions.githubusercontent.com --certificate-identity-regexp "${EXPECTED_TAG_SIGNER:?}" "$TAG"
  TAGS+=("$TAG")
done
if [[ "${PUSH_TAGS:-true}" == true ]]; then
  git -C "$ROOT" push origin "${TAGS[@]}"
fi
for TAG in "${TAGS[@]}"; do
  if ! gh release view "$TAG" >/dev/null 2>&1; then
    gh release create "$TAG" --title "$TAG" --notes "Signed release $TAG from $SOURCE_SHA. Artifact signatures, SLSA provenance, and test evidence verified before finalization."
  fi
done
echo "finalized ${#TAGS[@]} signed tag(s) and Release(s)"
