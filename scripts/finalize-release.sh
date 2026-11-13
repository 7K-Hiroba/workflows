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
export PLAN EVIDENCE SOURCE_SHA
python3 - <<'PY'
import json, os
from pathlib import Path
plan = json.load(open(os.environ["PLAN"]))
evidence = Path(os.environ["EVIDENCE"])
source = os.environ["SOURCE_SHA"].lower()
for component in plan["components"]:
    kind, name = component["kind"], component["name"]
    prefix = {"package": "catalog", "template": "template", "chart": "chart"}.get(kind)
    filename = f"artifact-{prefix}-{name}.json" if prefix else (f"artifact-smoke-{name}.json" if kind == "smoke" else ("artifact-extension-ui.json" if kind == "ui" else f"artifact-{kind}.json"))
    path = evidence / filename
    if not path.is_file():
        raise SystemExit(f"missing verified artifact evidence for {kind}/{name}: {filename}")
    data = json.load(open(path))
    if data.get("sourceSha", "").lower() != source:
        raise SystemExit(f"sourceSha mismatch for {filename}")
    if data.get("signature", {}).get("verified") is not True or data.get("provenance", {}).get("verified") is not True or data.get("testEvidence", {}).get("status") != "passed":
        raise SystemExit(f"artifact is not fully verified: {filename}")
PY
mapfile -t COMPONENTS < <(jq -r '.components[] | select(.kind != "smoke") | [.kind,.name,.path,.version] | @tsv' "$PLAN")
[[ ${#COMPONENTS[@]} -gt 0 ]] || { echo "no components to finalize" >&2; exit 2; }
git -C "$ROOT" config gpg.format x509
git -C "$ROOT" config gpg.x509.program gitsign
git -C "$ROOT" config gitsign.tokenProvider github-actions
TAGS=()
for row in "${COMPONENTS[@]}"; do
  IFS=$'\t' read -r KIND NAME _ VERSION <<< "$row"
  case "$KIND" in
    extension) TAG="extension-v$VERSION" ;;
    ui) TAG="ui-v$VERSION" ;;
    *) TAG="$NAME-v$VERSION" ;;
  esac
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
