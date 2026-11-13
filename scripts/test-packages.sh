#!/usr/bin/env bash
set -euo pipefail
ROOT=""
TYPE=""
PACKAGE=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --root) ROOT=$2; shift 2 ;;
    --type) TYPE=$2; shift 2 ;;
    --package) PACKAGE=$2; shift 2 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done
[[ -d "$ROOT" && -n "$TYPE" && "$PACKAGE" =~ ^[a-z0-9][a-z0-9-]*$ ]] || { echo "invalid package test arguments" >&2; exit 2; }
PACKAGE_DIR="$ROOT/packages/$PACKAGE"
[[ -f "$PACKAGE_DIR/tests/run.sh" ]] || { echo "missing tests/run.sh for $PACKAGE" >&2; exit 2; }
mkdir -p "$ROOT/evidence" "$ROOT/diagnostics"
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
  jq -n --arg lane "package-$TYPE-$PACKAGE" --arg status "$([[ $rc -eq 0 ]] && echo passed || echo failed)" \
    '{schema:"inari.lane-result.v1",lane:$lane,status:$status}' > "$ROOT/evidence/package-$PACKAGE.json"
  exit "$rc"
}
trap finish EXIT
if [[ "$TYPE" == kro-rgd ]]; then
  helm upgrade --install kro oci://registry.k8s.io/kro/charts/kro \
    --namespace kro-system --create-namespace --version 0.6.1 --wait --timeout 120s
  if [[ -d "$PACKAGE_DIR/tests/deps" ]]; then
    kubectl apply -f "$PACKAGE_DIR/tests/deps"
  fi
elif [[ "$TYPE" != policy-pack && "$TYPE" != platform-app ]]; then
  echo "unsupported package type: $TYPE" >&2
  exit 2
fi
bash "$PACKAGE_DIR/tests/run.sh"
