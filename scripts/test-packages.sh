#!/usr/bin/env bash
set -euo pipefail
ROOT=""
TYPE=""
PACKAGE=""
PACKAGE_PATH=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --root) ROOT=$2; shift 2 ;;
    --type) TYPE=$2; shift 2 ;;
    --package) PACKAGE=$2; shift 2 ;;
    --package-path) PACKAGE_PATH=$2; shift 2 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done
[[ -d "$ROOT" && -n "$TYPE" && "$PACKAGE" =~ ^[a-z0-9][a-z0-9-]*$ ]] || { echo "invalid package test arguments" >&2; exit 2; }
PACKAGE_PATH=${PACKAGE_PATH:-packages/$PACKAGE}
LIBRARY=$(cd "$(dirname "$0")/.." && pwd)
# shellcheck disable=SC1091
source "$LIBRARY/scripts/lib/stack-cluster.sh"
PACKAGE_PATH=$("${HIROBA_PYTHON:-python3}" -c 'import sys; from pathlib import Path; sys.path.insert(0,sys.argv[1]); from lib.paths import relative_path; print(relative_path(Path(sys.argv[2]), sys.argv[3], "package.path"))' "$LIBRARY/scripts" "$ROOT" "$PACKAGE_PATH")
PACKAGE_DIR="$ROOT/$PACKAGE_PATH"
[[ -f "$PACKAGE_DIR/tests/run.sh" ]] || { echo "missing tests/run.sh for $PACKAGE" >&2; exit 2; }
mkdir -p "$ROOT/evidence" "$ROOT/diagnostics"
SOURCE_SHA=$(git -C "$ROOT" rev-parse HEAD)
WORK=$(mktemp -d)
CLUSTER="hiroba-package-${GITHUB_RUN_ID:-local}-$$"
export HIROBA_STACK_WORK="$WORK"
export HIROBA_STACK_CLUSTER="$CLUSTER"
finish() {
  rc=$?
  if [[ $rc -ne 0 ]]; then
    {
      kubectl get all -A -o wide || true
      kubectl get rgd -A -o yaml || true
      kubectl get crd -o name || true
      kubectl get events -A --sort-by=.lastTimestamp || true
      kubectl logs -n kro-system deploy/kro --tail=200 || true
    } > "$ROOT/diagnostics/$PACKAGE.txt" 2>&1
  fi
  if [[ "$TYPE" == kro-rgd || "$TYPE" == policy-pack ]]; then
    kind delete cluster --name "$CLUSTER" || true
  fi
  jq -n --arg lane "package-$TYPE-$PACKAGE" --arg status "$([[ $rc -eq 0 ]] && echo passed || echo failed)" --arg sourceSha "$SOURCE_SHA" \
    '{schema:"inari.lane-result.v1",lane:$lane,status:$status,sourceSha:$sourceSha}' > "$ROOT/evidence/package-$PACKAGE.json"
  rm -rf "$WORK"
  exit "$rc"
}
trap finish EXIT
if [[ "$TYPE" == kro-rgd || "$TYPE" == policy-pack ]]; then
  create_kind_cluster "$CLUSTER"
fi
if [[ "$TYPE" == kro-rgd ]]; then
  setup_kro
  if [[ -d "$PACKAGE_DIR/tests/deps" ]]; then
    kubectl apply -f "$PACKAGE_DIR/tests/deps"
  fi
elif [[ "$TYPE" != policy-pack && "$TYPE" != platform-app && "$TYPE" != manifests ]]; then
  echo "unsupported package type: $TYPE" >&2
  exit 2
fi
bash "$PACKAGE_DIR/tests/run.sh"
