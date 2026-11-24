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
PYTHON=${HIROBA_PYTHON:-python3}
# shellcheck disable=SC1091
source "$LIBRARY/scripts/lib/stack-cluster.sh"
WORK=$(mktemp -d)
CLUSTER="hiroba-chart-${GITHUB_RUN_ID:-local}-$$"
CLUSTER_CREATE_ATTEMPTED=false
CLUSTER_CREATE_COUNT=0
CLUSTER_DELETE_COUNT=0
CLEANED_UP=true
LIFECYCLE=false
RELEASE_NAME=""
CHART_NAME=""
STARTED=$(date +%s)
STARTED_AT=$(date -u +%Y-%m-%dT%H:%M:%SZ)
STATE="$WORK/chart-lifecycle-state.json"
PACKAGES="$WORK/chart-lifecycle-packages.json"
mkdir -p "$ROOT/diagnostics"
declare -A PHASE_STARTED=()
declare -A PHASE_DURATION=()

lifecycle_py() {
  PYTHONPATH="$LIBRARY/scripts${PYTHONPATH:+:$PYTHONPATH}" "$PYTHON" -m lib.chart_lifecycle "$@"
}

finish() {
  rc=$?
  trap - EXIT INT TERM
  if [[ $rc -ne 0 ]]; then
    kubectl get all,events -A -o wide > "$ROOT/diagnostics/chart-$(basename "$CHART").txt" 2>&1 || true
    if [[ "$LIFECYCLE" == true ]]; then
      {
        helm list --namespace default -o json || true
        if [[ -n "$RELEASE_NAME" ]]; then
          helm status "$RELEASE_NAME" --namespace default || true
          helm history "$RELEASE_NAME" --namespace default || true
          if helm get manifest "$RELEASE_NAME" --namespace default > "$WORK/helm-manifest.yaml"; then
            lifecycle_py redact-manifest --input "$WORK/helm-manifest.yaml"
          fi
        fi
        kubectl get events -A --sort-by=.lastTimestamp || true
        kubectl get pods -n default -o name | while read -r pod; do
          kubectl logs -n default "$pod" --all-containers=true --tail=200 || true
        done
        if [[ -f "$ROOT/diagnostics/chart-$(basename "$CHART")-assertions.txt" ]]; then
          cat "$ROOT/diagnostics/chart-$(basename "$CHART")-assertions.txt"
        fi
        if [[ "$CLUSTER_CREATE_ATTEMPTED" == true ]]; then kind export logs "$WORK/kind-logs" --name "$CLUSTER" || true; fi
      } >> "$ROOT/diagnostics/chart-$(basename "$CHART").txt" 2>&1 || true
    fi
  fi
  delete_rc=0
  if [[ "$CLUSTER_CREATE_ATTEMPTED" == true ]]; then kind delete cluster --name "$CLUSTER" || delete_rc=$?; fi
  if [[ "$CLUSTER_CREATE_ATTEMPTED" == true ]]; then
    CLEANED_UP=false
    if [[ "$LIFECYCLE" == true ]]; then
      if [[ $delete_rc -eq 0 ]]; then
        CLUSTER_DELETE_COUNT=1
        CLEANED_UP=true
      else
        rc=1
      fi
    fi
  fi
  if [[ "$LIFECYCLE" == true && -f "$STATE" ]]; then
    install_duration=-1
    upgrade_duration=-1
    if [[ -n "${PHASE_STARTED[install]:-}" ]]; then
      install_duration=${PHASE_DURATION[install]:-$(( $(date +%s) - PHASE_STARTED[install] ))}
    fi
    if [[ -n "${PHASE_STARTED[upgrade]:-}" ]]; then
      upgrade_duration=${PHASE_DURATION[upgrade]:-$(( $(date +%s) - PHASE_STARTED[upgrade] ))}
    fi
    outcome=failed
    if [[ $rc -eq 0 ]]; then outcome=passed; fi
    lifecycle_py finish --state "$STATE" --output "$ROOT/evidence/chart-lifecycle-$(basename "$CHART").json" \
      --outcome "$outcome" --create-count "$CLUSTER_CREATE_COUNT" --delete-count "$CLUSTER_DELETE_COUNT" \
      --cleaned-up "$CLEANED_UP" --install-duration "$install_duration" --upgrade-duration "$upgrade_duration" \
      --total-duration "$(( $(date +%s) - STARTED ))" || rc=$?
  fi
  rm -rf "$WORK"
  exit "$rc"
}
trap finish EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

"$PYTHON" "$LIBRARY/scripts/prepare-chart.py" --chart "$ROOT/$CHART"
"$PYTHON" "$LIBRARY/scripts/chart-test-config.py" --root "$ROOT" --chart "$CHART" > "$WORK/chart-test.json"
if [[ $(jq -r 'has("upgrade")' "$WORK/chart-test.json") == true ]]; then
  LIFECYCLE=true
  if [[ "$STACK_COVERED" == true ]]; then
    echo "stack-covered chart cannot silently skip its declared chart upgrade lifecycle" >&2
    exit 2
  fi
fi

ct lint --config "$ROOT/ci/ct.yaml" --chart-yaml-schema "$ROOT/ci/chart_schema.yaml" \
  --lint-conf "$ROOT/ci/lintconf.yaml" --skip-helm-dependencies --charts "$ROOT/$CHART"

if [[ "$LIFECYCLE" == true ]]; then
  WORKFLOW_SHA=${WORKFLOW_SHA:-}
  [[ "$WORKFLOW_SHA" =~ ^[0-9a-fA-F]{40}$ ]] || { echo "WORKFLOW_SHA must be a full commit SHA for chart lifecycle evidence" >&2; exit 2; }
  SOURCE_SHA=$(git -C "$ROOT" rev-parse HEAD)
  PR_HEAD_SHA=""
  if [[ -n "${GITHUB_EVENT_PATH:-}" && -f "$GITHUB_EVENT_PATH" ]]; then
    PR_HEAD_SHA=$(jq -r '.pull_request.head.sha // empty' "$GITHUB_EVENT_PATH")
  fi
  lifecycle_py preflight --root "$ROOT" --chart "$CHART" --config "$WORK/chart-test.json" --work "$WORK" > "$PACKAGES"
  lifecycle_py init --packages "$PACKAGES" --output "$STATE" --chart "$CHART" --cluster "$CLUSTER" \
    --source-sha "$SOURCE_SHA" --pr-head-sha "$PR_HEAD_SHA" --workflow-sha "$WORKFLOW_SHA" \
    --run-id "${GITHUB_RUN_ID:-local}" --run-attempt "${GITHUB_RUN_ATTEMPT:-1}" --started-at "$STARTED_AT"
  RELEASE_NAME=$(jq -r .releaseName "$STATE")
  CHART_NAME=$(jq -r .chartName "$STATE")
fi

if [[ "$STACK_COVERED" == true ]]; then
  while read -r values; do
    [[ -n "$values" ]] || continue
    helm template "$(basename "$CHART")" "$ROOT/$CHART" --values "$ROOT/$values" > /dev/null
  done < <(jq -r '.install.values[]' "$WORK/chart-test.json")
  echo "chart is covered by the declared stack lifecycle; skipping duplicate kind install"
  exit 0
fi

CLUSTER_CREATE_ATTEMPTED=true
create_kind_cluster "$CLUSTER"
CLUSTER_CREATE_COUNT=1
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

verify_release() {
  local revision=$1 version=$2
  helm list --namespace default --filter "^${RELEASE_NAME}$" -o json | jq -e \
    --arg name "$RELEASE_NAME" --arg chart "$CHART_NAME-$version" --argjson revision "$revision" \
    'length == 1 and .[0].name == $name and .[0].namespace == "default" and .[0].status == "deployed" and .[0].chart == $chart and (.[0].revision | tonumber) == $revision' >/dev/null
}

run_lifecycle_phase() {
  local phase=$1 label=$2 revision=$3 timeout=$4 package version package_digest
  PHASE_STARTED[$phase]=$(date +%s)
  package=$(jq -r --arg slot "$label" '.[$slot].path' "$PACKAGES")
  version=$(jq -r --arg slot "$label" '.[$slot].version' "$PACKAGES")
  package_digest=$(jq -r --arg slot "$label" '.[$slot].packageDigest' "$PACKAGES")
  lifecycle_py phase --state "$STATE" --phase "$phase" --status running
  value_args=()
  while read -r values; do
    [[ -n "$values" ]] || continue
    value_args+=(--values "$ROOT/$values")
  done < <(jq -r '.install.values[]' "$WORK/chart-test.json")
  if [[ "$phase" == install ]]; then
    helm list --namespace default --filter "^${RELEASE_NAME}$" -o json | jq -e 'length == 0' >/dev/null
    helm install "$RELEASE_NAME" "$package" --namespace default --wait --wait-for-jobs --timeout "$timeout" "${value_args[@]}"
  else
    helm upgrade "$RELEASE_NAME" "$package" --namespace default --wait --wait-for-jobs --timeout "$timeout" "${value_args[@]}"
  fi
  verify_release "$revision" "$version"
  lifecycle_py phase --state "$STATE" --phase "$phase" --status running --assertions running
  HIROBA_CHART_PHASE="$phase" HIROBA_CHART_ROOT="$ROOT" HIROBA_CHART_PATH="$CHART" HIROBA_CHART_WORK="$WORK" \
    HIROBA_CHART_PACKAGE="$package" HIROBA_CHART_VERSION="$version" HIROBA_CHART_DIGEST="$package_digest" \
    HIROBA_CHART_RELEASE="$RELEASE_NAME" HIROBA_CHART_NAMESPACE=default HIROBA_CHART_CLUSTER="$CLUSTER" \
    bash "$ROOT/$(jq -r .upgrade.assertions "$WORK/chart-test.json")" 2>&1 | tee -a "$ROOT/diagnostics/chart-$(basename "$CHART")-assertions.txt"
  verify_release "$revision" "$version"
  PHASE_DURATION[$phase]=$(( $(date +%s) - PHASE_STARTED[$phase] ))
  lifecycle_py phase --state "$STATE" --phase "$phase" --status passed --assertions passed \
    --revision "$revision" --duration "${PHASE_DURATION[$phase]}"
}

if [[ "$LIFECYCLE" == true ]]; then
  install_timeout=$(jq -r .install.timeout "$WORK/chart-test.json")
  upgrade_timeout=$(jq -r .upgrade.timeout "$WORK/chart-test.json")
  run_lifecycle_phase install previous 1 "$install_timeout"
  run_lifecycle_phase upgrade current 2 "$upgrade_timeout"
  lifecycle_py verify-unchanged --packages "$PACKAGES"
else
  timeout=$(jq -r .install.timeout "$WORK/chart-test.json")
  ct install --config "$ROOT/ci/ct.yaml" --charts "$ROOT/$CHART" --helm-extra-args "--timeout $timeout"
fi
