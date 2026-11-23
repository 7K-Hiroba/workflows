#!/usr/bin/env bash
set -euo pipefail

ROOT=""
CHART=""
STACK_COVERED=false
while [[ $# -gt 0 ]]; do
  case "$1" in
    --root) ROOT=$2; shift 2 ;;
    --chart) CHART=$2; shift 2 ;;
    --stack-covered) STACK_COVERED=$2; shift 2 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done
[[ -d "$ROOT" && -n "$CHART" ]] || { echo "chart root and path are required" >&2; exit 2; }
[[ "$STACK_COVERED" == true || "$STACK_COVERED" == false ]] || { echo "stack-covered must be true or false" >&2; exit 2; }
ROOT=$(cd "$ROOT" && pwd)
LIBRARY=$(cd "$(dirname "$0")/.." && pwd)
# shellcheck disable=SC1091
source "$LIBRARY/scripts/lib/stack-cluster.sh"
WORK=$(mktemp -d)
CLUSTER="hiroba-chart-${GITHUB_RUN_ID:-local}-$$"
CLUSTER_STARTED=false
mkdir -p "$ROOT/diagnostics"
finish() {
  rc=$?
  trap - EXIT
  if [[ $rc -ne 0 ]]; then
    kubectl get all,events -A -o wide > "$ROOT/diagnostics/chart-$(basename "$CHART").txt" 2>&1 || true
  fi
  if [[ "$CLUSTER_STARTED" == true ]]; then kind delete cluster --name "$CLUSTER" || true; fi
  rm -rf "$WORK"
  exit "$rc"
}
trap finish EXIT

python3 "$LIBRARY/scripts/prepare-chart.py" --chart "$ROOT/$CHART"
python3 "$LIBRARY/scripts/chart-test-config.py" --root "$ROOT" --chart "$CHART" > "$WORK/chart-test.json"
ct lint --config "$ROOT/ci/ct.yaml" --chart-yaml-schema "$ROOT/ci/chart_schema.yaml" \
  --lint-conf "$ROOT/ci/lintconf.yaml" --skip-helm-dependencies --charts "$ROOT/$CHART"

if [[ "$STACK_COVERED" == true ]]; then
  while read -r values; do
    [[ -n "$values" ]] || continue
    helm template "$(basename "$CHART")" "$ROOT/$CHART" --values "$ROOT/$values" > /dev/null
  done < <(jq -r '.install.values[]' "$WORK/chart-test.json")
  echo "chart is covered by the declared stack lifecycle; skipping duplicate kind install"
  exit 0
fi

create_kind_cluster "$CLUSTER"
CLUSTER_STARTED=true
if [[ $(jq -r '.image != null' "$WORK/chart-test.json") == true ]]; then
  repository=$(jq -r .image.repository "$WORK/chart-test.json")
  tag=$(jq -r .image.tag "$WORK/chart-test.json")
  context=$(jq -r .image.context "$WORK/chart-test.json")
  docker build -t "$repository:$tag" "$ROOT/$context"
  kind load docker-image "$repository:$tag" --name "$CLUSTER"
fi
while read -r dependency; do
  [[ -n "$dependency" ]] || continue
  kubectl apply -f "$ROOT/$dependency"
done < <(jq -r '.dependencies[]' "$WORK/chart-test.json")
timeout=$(jq -r .install.timeout "$WORK/chart-test.json")
ct install --config "$ROOT/ci/ct.yaml" --charts "$ROOT/$CHART" --helm-extra-args "--timeout $timeout"
