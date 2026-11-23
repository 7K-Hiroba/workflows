#!/usr/bin/env bash
set -euo pipefail

ROOT=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --root) ROOT=$2; shift 2 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done
[[ -d "$ROOT" ]] || { echo "--root must be a consumer directory" >&2; exit 2; }
ROOT=$(cd "$ROOT" && pwd)
LIBRARY=$(cd "$(dirname "$0")/.." && pwd)
PYTHON=${HIROBA_PYTHON:-python3}
PLAN=$("$PYTHON" "$LIBRARY/scripts/stack-test-config.py" --root "$ROOT")
if [[ $(jq -r .enabled <<< "$PLAN") != true ]]; then
  echo "non-stack repository: stack lifecycle is not applicable"
  exit 0
fi

# shellcheck disable=SC1091
source "$LIBRARY/scripts/lib/stack-cluster.sh"
SOURCE_SHA=$(git -C "$ROOT" rev-parse HEAD)
WORKFLOW_SHA=${WORKFLOW_SHA:-}
[[ "$WORKFLOW_SHA" =~ ^[0-9a-fA-F]{40}$ ]] || { echo "WORKFLOW_SHA must be a full commit SHA" >&2; exit 2; }
WORK=$(mktemp -d)
CLUSTER="hiroba-stack-${GITHUB_RUN_ID:-local}-${GITHUB_RUN_ATTEMPT:-1}-$$"
export HIROBA_STACK_ROOT="$ROOT"
export HIROBA_STACK_WORK="$WORK"
export HIROBA_STACK_CLUSTER="$CLUSTER"
export KUBECONFIG="$WORK/kubeconfig"
mkdir -p "$ROOT/evidence" "$ROOT/diagnostics"
STARTED=$(date +%s)
STARTED_AT=$(date -u +%Y-%m-%dT%H:%M:%SZ)
CLUSTER_CREATE_COUNT=0
CLUSTER_DELETE_COUNT=0
CLEANED_UP=false
CURRENT_PHASE=setup
declare -A PHASE_STARTED=()
declare -A PHASE_DURATION=()

append_phase_evidence() {
  local phase=$1 duration=0
  if [[ -n "${PHASE_STARTED[$phase]:-}" ]]; then
    duration=${PHASE_DURATION[$phase]:-$(( $(date +%s) - PHASE_STARTED[$phase] ))}
  fi
  if [[ -f "$WORK/$phase-result.json" ]]; then
    PHASES_JSON=$(jq -c --argjson phase "$(cat "$WORK/$phase-result.json")" --argjson duration "$duration" \
      '. + [$phase + {durationSeconds:$duration}]' <<< "$PHASES_JSON")
  fi
}

finish() {
  rc=$?
  trap - EXIT
  if [[ $rc -ne 0 ]]; then
    suite_path=$(jq -r .path <<< "$PLAN")
    diagnostics=$(jq -r '.diagnostics // empty' <<< "$PLAN")
    if [[ -n "$diagnostics" ]]; then
      HIROBA_STACK_PHASE="$CURRENT_PHASE" bash "$ROOT/$suite_path/$diagnostics" > "$ROOT/diagnostics/stack-custom.txt" 2>&1 || true
    fi
    stack_generic_diagnostics "$ROOT/diagnostics/stack-lifecycle.txt"
  fi
  stop_stack_port_forwards
  if [[ $CLUSTER_CREATE_COUNT -gt 0 ]]; then
    if kind delete cluster --name "$CLUSTER"; then
      CLUSTER_DELETE_COUNT=$((CLUSTER_DELETE_COUNT + 1))
      CLEANED_UP=true
    else
      rc=1
    fi
  fi
  FINISHED_AT=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  TOTAL_DURATION=$(( $(date +%s) - STARTED ))
  PHASES_JSON='[]'
  append_phase_evidence install
  append_phase_evidence upgrade
  rm -rf "$WORK"
  CACHE_JSON=$(jq -c '{cacheKey:.cacheKey,cacheHit:.cacheHit,tools:.tools}' "${HIROBA_TOOL_CACHE_REPORT:-${RUNNER_TEMP:-/tmp}/hiroba-tool-cache.json}" 2>/dev/null || jq -nc --arg key "$(jq -r .cacheKey <<< "$PLAN")" '{cacheKey:$key,cacheHit:false,tools:[]}')
  jq -n \
    --arg status "$([[ $rc -eq 0 ]] && echo passed || echo failed)" \
    --arg sourceSha "$SOURCE_SHA" --arg workflowSha "$WORKFLOW_SHA" \
    --arg runId "${GITHUB_RUN_ID:-local}" --arg runAttempt "${GITHUB_RUN_ATTEMPT:-1}" \
    --arg startedAt "$STARTED_AT" --arg finishedAt "$FINISHED_AT" \
    --argjson profiles "$(jq -c .setupProfiles <<< "$PLAN")" \
    --argjson covers "$(jq -c .covers <<< "$PLAN")" \
    --argjson fixtureOnly "$(jq -c .fixtureOnly <<< "$PLAN")" \
    --argjson cache "$CACHE_JSON" --argjson phases "$PHASES_JSON" \
    --argjson createCount "$CLUSTER_CREATE_COUNT" --argjson deleteCount "$CLUSTER_DELETE_COUNT" \
    --argjson cleanedUp "$CLEANED_UP" --argjson totalDuration "$TOTAL_DURATION" \
    '{schema:"inari.lane-result.v1",lane:"stack-lifecycle",status:$status,sourceSha:$sourceSha,workflowSha:$workflowSha,runId:$runId,runAttempt:$runAttempt,startedAt:$startedAt,finishedAt:$finishedAt,setupProfiles:$profiles,covers:$covers,fixtureOnly:$fixtureOnly,cache:$cache,phases:$phases,clusterCreateCount:$createCount,clusterDeleteCount:$deleteCount,freshState:true,cleanedUp:$cleanedUp,functionalE2E:false,deployedReadiness:"not-tested",totalDurationSeconds:$totalDuration}' \
    > "$ROOT/evidence/stack-lifecycle.json"
  exit "$rc"
}
trap finish EXIT INT TERM

run_phase() {
  local phase=$1 script timeout
  CURRENT_PHASE=$phase
  script=$(jq -r --arg phase "$phase" '.[$phase].script' <<< "$PLAN")
  timeout=$(jq -r --arg phase "$phase" '.[$phase].timeout' <<< "$PLAN")
  PHASE_STARTED[$phase]=$(date +%s)
  HIROBA_STACK_PHASE="$phase" timeout "$timeout" bash "$ROOT/$(jq -r .path <<< "$PLAN")/$script"
  "$PYTHON" - "$LIBRARY/scripts" "$WORK/$phase-result.json" "$phase" <<'PY'
import sys
sys.path.insert(0, sys.argv[1])
from lib.stack_testing import validate_phase_result
validate_phase_result(__import__('pathlib').Path(sys.argv[2]), sys.argv[3])
PY
  PHASE_DURATION[$phase]=$(( $(date +%s) - PHASE_STARTED[$phase] ))
}

kind create cluster --name "$CLUSTER" --image "$(stack_pin .kind.nodeImage)" --wait 120s
CLUSTER_CREATE_COUNT=1
mapfile -t PROFILES < <(jq -r '.setupProfiles[]' <<< "$PLAN")
run_stack_setup_profiles "${PROFILES[@]}"
run_phase install
run_phase upgrade
"$PYTHON" - "$WORK/install-result.json" "$WORK/upgrade-result.json" <<'PY'
import json, sys
install = json.load(open(sys.argv[1]))
upgrade = json.load(open(sys.argv[2]))
if install["contentDigest"] == upgrade["contentDigest"]:
    raise SystemExit("install and upgrade content identities must be distinct")
PY
