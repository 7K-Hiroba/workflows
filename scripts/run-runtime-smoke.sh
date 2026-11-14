#!/usr/bin/env bash
set -euo pipefail

ROOT=""
MODE=local
PROFILE=ci
APP_REF=""
SUITE_REF=""
WORKFLOW_SHA=${WORKFLOW_SHA:-}
while [[ $# -gt 0 ]]; do
  case "$1" in
    --root) ROOT=$2; shift 2 ;;
    --mode) MODE=$2; shift 2 ;;
    --profile) PROFILE=$2; shift 2 ;;
    --app-ref) APP_REF=$2; shift 2 ;;
    --suite-ref) SUITE_REF=$2; shift 2 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done
[[ "$PROFILE" == ci ]] || { echo "runtime smoke driver permits only profile=ci; stage/prod belong to the gated environment verifier" >&2; exit 2; }
[[ "$MODE" == local || "$MODE" == oci ]] || { echo "mode must be local or oci" >&2; exit 2; }
if [[ "$MODE" == oci ]]; then
  for ref in "$APP_REF" "$SUITE_REF"; do
    [[ "$ref" =~ @sha256:[0-9a-fA-F]{64}$ ]] || { echo "OCI mode requires exact app and suite sha256 digest refs" >&2; exit 2; }
  done
fi
[[ -d "$ROOT" ]] || { echo "--root must be a consumer directory" >&2; exit 2; }
ROOT=$(cd "$ROOT" && pwd)
LIBRARY=$(cd "$(dirname "$0")/.." && pwd)
SOURCE_SHA=$(git -C "$ROOT" rev-parse HEAD)
python3 "$LIBRARY/scripts/validate-repository.py" --root "$ROOT"
python3 "$LIBRARY/scripts/discover-components.py" --root "$ROOT" --all > "$ROOT/evidence-runtime-plan.json"
APP=$(jq -r '.app' "$ROOT/evidence-runtime-plan.json")
TARGET=$(jq -r '.components[] | select(.kind == "smoke") | .targetComponent' "$ROOT/evidence-runtime-plan.json")
CHART=$(jq -r --arg target "$TARGET" '.components[] | select(.kind == "chart" and .path == $target) | .path' "$ROOT/evidence-runtime-plan.json")
EXTENSION=$(jq -r '.components[] | select(.kind == "extension") | .path' "$ROOT/evidence-runtime-plan.json")
[[ -n "$APP" && -n "$CHART" && -n "$EXTENSION" ]] || { echo "runtime smoke requires extension, chart, and smoke components" >&2; exit 2; }
mkdir -p "$ROOT/diagnostics" "$ROOT/evidence"
WORK=$(mktemp -d)
CLUSTER="hiroba-smoke-${GITHUB_RUN_ID:-local}-$$"
WORKFLOW_NAME=""
SUITE_DIR="$ROOT/tests/smoke"
finish() {
  rc=$?
  if [[ $rc -ne 0 ]]; then
    {
      kubectl get all,workflows,events -A -o wide || true
      kubectl get events -A --sort-by=.lastTimestamp || true
      kubectl logs -A -l "app.kubernetes.io/name=$APP" --all-containers=true --tail=200 || true
      if [[ -n "$WORKFLOW_NAME" ]]; then argo get "$WORKFLOW_NAME" -n default || true; argo logs "$WORKFLOW_NAME" -n default || true; fi
      kind export logs "$WORK/kind-logs" --name "$CLUSTER" || true
    } > "$ROOT/diagnostics/runtime-smoke.txt" 2>&1
  fi
  if [[ -n "$WORKFLOW_NAME" ]]; then
    argo get "$WORKFLOW_NAME" -n default -o json > "$ROOT/evidence/argo-workflow.json" 2>/dev/null || true
  fi
  jq -n --arg lane runtime-smoke --arg status "$([[ $rc -eq 0 ]] && echo passed || echo failed)" \
    --arg app "$APP" --arg mode "$MODE" --arg profile "$PROFILE" --arg sourceSha "$SOURCE_SHA" \
    '{schema:"inari.lane-result.v1",lane:$lane,status:$status,app:$app,mode:$mode,profile:$profile,sourceSha:$sourceSha}' > "$ROOT/evidence/runtime-smoke.json"
  # The unique cluster may exist even when creation or readiness fails partway through.
  kind delete cluster --name "$CLUSTER" || true
  rm -rf "$WORK"
  rm -f "$ROOT/evidence-runtime-plan.json"
  exit "$rc"
}
trap finish EXIT

KIND_IMAGE='kindest/node:v1.31.2@sha256:0526eb5cd8d892ed79b56feb48d17eeee1f719f55d5c35cef468f053caffad32'
ARGO_COMMIT='43021573c5a35cbafae009043c132dfcef43a112'
kind create cluster --name "$CLUSTER" --image "$KIND_IMAGE" --wait 120s
if [[ "$MODE" == local ]]; then
  docker build -t "$APP:ci" "$ROOT/$EXTENSION"
  kind load docker-image "$APP:ci" --name "$CLUSTER"
  helm upgrade --install "$APP" "$ROOT/$CHART" --namespace default \
    --values "$SUITE_DIR/values.yaml" --wait --timeout 5m
else
  [[ "$WORKFLOW_SHA" =~ ^[0-9a-fA-F]{40}$ ]] || { echo "OCI mode requires the resolved workflow SHA" >&2; exit 2; }
  [[ "${GITHUB_REPOSITORY:-}" =~ ^[^/]+/[^/]+$ ]] || { echo "OCI mode requires the source repository" >&2; exit 2; }
  SOURCE_SHA=$(git -C "$ROOT" rev-parse HEAD)
  CHART_NAME=$(jq -r --arg target "$TARGET" '.components[] | select(.kind == "chart" and .path == $target) | .name' "$ROOT/evidence-runtime-plan.json")
  CHART_VERSION=$(jq -r --arg target "$TARGET" '.components[] | select(.kind == "chart" and .path == $target) | .version' "$ROOT/evidence-runtime-plan.json")
  TARGET_ID=$(python3 -c 'import sys,yaml; print(yaml.safe_load(open(sys.argv[1]))["target"]["id"])' "$SUITE_DIR/suite.yaml")
  TARGET_VERSION=$(python3 -c 'import sys,yaml; print(yaml.safe_load(open(sys.argv[1]))["target"]["version"])' "$SUITE_DIR/suite.yaml")
  for ref in "$APP_REF" "$SUITE_REF"; do
    repository=${ref%@*}
    if [[ "$ref" == "$APP_REF" ]]; then
      workflow_path=.github/workflows/release-chart.yml
      expected_publisher="^https://github\\.com/7K-Hiroba/workflows/\\.github/workflows/release-chart\\.yml@${WORKFLOW_SHA}$"
      media_type=application/vnd.cncf.helm.chart.v1
      required="validate chart"
      release_tag="$CHART_NAME-v$CHART_VERSION"
    else
      workflow_path=.github/workflows/release-smoke-suite.yml
      expected_publisher="^https://github\\.com/7K-Hiroba/workflows/\\.github/workflows/release-smoke-suite\\.yml@${WORKFLOW_SHA}$"
      media_type=application/vnd.inari.smoke.suite.v1+yaml
      required="validate runtime-smoke"
      release_tag="$TARGET_ID-v$TARGET_VERSION"
    fi
    ARTIFACT_REF="$ref" ARTIFACT_REPOSITORY="$repository" ARTIFACT_DIGEST="${ref#*@}" MEDIA_TYPE="$media_type" \
      SOURCE_REPOSITORY="$GITHUB_REPOSITORY" SOURCE_SHA="$SOURCE_SHA" WORKFLOW_SHA="$WORKFLOW_SHA" WORKFLOW_PATH="$workflow_path" \
      REQUIRED_LANES="$required" RELEASE_TAG="$release_tag" EXPECTED_PUBLISHER="$expected_publisher" \
      "$LIBRARY/scripts/verify-release.sh"
  done
  mkdir -p "$WORK/suite"
  oras pull --plain-http=false --output "$WORK/suite" "$SUITE_REF"
  SUITE_DIR="$WORK/suite"
  VERSION=$(python3 -c 'import sys,yaml; print(yaml.safe_load(open(sys.argv[1]))["target"]["version"])' "$SUITE_DIR/suite.yaml")
  APP_REPOSITORY=${APP_REF%@*}
  crane digest "$APP_REPOSITORY:$VERSION" | grep -Fx "${APP_REF#*@}"
  helm upgrade --install "$APP" "oci://$APP_REPOSITORY" --namespace default --version "$VERSION" --wait --timeout 5m
  crane digest "$APP_REPOSITORY:$VERSION" | grep -Fx "${APP_REF#*@}"
fi
kubectl wait --for=condition=Available deployment -l "app.kubernetes.io/name=$APP" --namespace default --timeout 120s
kubectl create namespace argo --dry-run=client -o yaml | kubectl apply -f -
kubectl create -n argo -f "https://raw.githubusercontent.com/argoproj/argo-workflows/$ARGO_COMMIT/manifests/quick-start-minimal.yaml"
# The workflow's default service account needs the canonical executor role in its own namespace.
kubectl create --namespace default -f "https://raw.githubusercontent.com/argoproj/argo-workflows/$ARGO_COMMIT/manifests/quick-start/base/executor/emissary/executor-role.yaml"
kubectl create --namespace default -f "https://raw.githubusercontent.com/argoproj/argo-workflows/$ARGO_COMMIT/manifests/quick-start/base/executor-default-rolebinding.yaml"
# The pinned quick-start names a controller-test artifact plugin. This suite is artifactless.
kubectl patch configmap workflow-controller-configmap --namespace argo --type=json \
  --patch='[{"op":"remove","path":"/data/artifactRepository"}]'
kubectl rollout restart deployment/workflow-controller --namespace argo
kubectl wait --for=condition=Available deployment -n argo --all --timeout 180s
WORKFLOW_FILE=$(python3 -c 'import sys,yaml; print(yaml.safe_load(open(sys.argv[1]))["workflowTemplate"])' "$SUITE_DIR/suite.yaml")
kubectl apply -f "$SUITE_DIR/$WORKFLOW_FILE"
argo lint "$SUITE_DIR/$WORKFLOW_FILE"
WORKFLOW_NAME=$(argo submit --from "workflowtemplate/$APP" --namespace default -o name)
TIMEOUT=$(python3 -c 'import sys,yaml; print(yaml.safe_load(open(sys.argv[1]))["timeout"])' "$SUITE_DIR/suite.yaml")
timeout "$TIMEOUT" argo wait "$WORKFLOW_NAME" --namespace default
argo get "$WORKFLOW_NAME" --namespace default -o json | jq -e '.status.phase == "Succeeded"' >/dev/null
