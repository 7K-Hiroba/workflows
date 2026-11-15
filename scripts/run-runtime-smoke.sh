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
TARGET=$(jq -r 'first(.components[] | select(.kind == "smoke") | .targetComponent) // empty' "$ROOT/evidence-runtime-plan.json")
SMOKE_PATH=$(jq -r 'first(.components[] | select(.kind == "smoke") | .path) // empty' "$ROOT/evidence-runtime-plan.json")
ADAPTER=$(jq -r 'first(.components[] | select(.kind == "smoke") | .targetAdapter) // "helm"' "$ROOT/evidence-runtime-plan.json")
FIXTURE_ONLY=$(jq -r 'first(.components[] | select(.kind == "smoke") | .fixtureOnly) // false' "$ROOT/evidence-runtime-plan.json")
EXECUTABLE_PROFILES=$(jq -c 'first(.components[] | select(.kind == "smoke") | .executableProfiles) // ["ci", "stage", "prod"]' "$ROOT/evidence-runtime-plan.json")
EVIDENCE_SCOPE=$(jq -r 'first(.components[] | select(.kind == "smoke") | .evidenceScope) // "application"' "$ROOT/evidence-runtime-plan.json")
APP_EVIDENCE_ELIGIBLE=$(jq -r 'first(.components[] | select(.kind == "smoke") | .appEvidenceEligible) // true' "$ROOT/evidence-runtime-plan.json")
SUITE_DIR="$ROOT/$SMOKE_PATH"
TARGET_ID=$(python3 -c 'import sys,yaml; print(yaml.safe_load(open(sys.argv[1]))["target"]["id"])' "$SUITE_DIR/suite.yaml")
TARGET_VERSION=$(python3 -c 'import sys,yaml; print(yaml.safe_load(open(sys.argv[1]))["target"]["version"])' "$SUITE_DIR/suite.yaml")
MANIFEST_PATH=$(python3 -c 'import sys,yaml; target=yaml.safe_load(open(sys.argv[1]))["target"]; print(target.get("adapter", {}).get("path", ""))' "$SUITE_DIR/suite.yaml")
ARTIFACT_PATH=$(python3 -c 'import sys,yaml; target=yaml.safe_load(open(sys.argv[1]))["target"]; print(target.get("adapter", {}).get("artifactPath", ""))' "$SUITE_DIR/suite.yaml")
HAS_ADAPTER=$(python3 -c 'import sys,yaml; print(str("adapter" in yaml.safe_load(open(sys.argv[1]))["target"]).lower())' "$SUITE_DIR/suite.yaml")
[[ -n "$APP" && -n "$SMOKE_PATH" && -n "$TARGET_ID" && -n "$TARGET_VERSION" ]] || { echo "runtime smoke requires a smoke component and target identity" >&2; exit 2; }
jq -e --arg profile "$PROFILE" 'first(.components[] | select(.kind == "smoke") | .executableProfiles) // ["ci", "stage", "prod"] | index($profile) != null' "$ROOT/evidence-runtime-plan.json" >/dev/null || {
  echo "profile $PROFILE is not executable for this smoke suite" >&2
  exit 2
}
if [[ "$FIXTURE_ONLY" == true && "$MODE" != local ]]; then
  echo "fixtureOnly smoke suites are local/CI-only and cannot use OCI app verification" >&2
  exit 2
fi
CHART=$(jq -r --arg target "$TARGET" 'first(.components[] | select(.kind == "chart" and .path == $target) | .path) // empty' "$ROOT/evidence-runtime-plan.json")
case "$ADAPTER" in
  helm)
    [[ -n "$TARGET" && -n "$CHART" ]] || { echo "helm smoke requires an existing target chart" >&2; exit 2; }
    ;;
  manifests)
    [[ -n "$MANIFEST_PATH" ]] || { echo "manifests smoke requires adapter.path" >&2; exit 2; }
    ;;
  *) echo "unsupported smoke target adapter: $ADAPTER" >&2; exit 2 ;;
esac
mkdir -p "$ROOT/diagnostics" "$ROOT/evidence"
WORK=$(mktemp -d)
CLUSTER="hiroba-smoke-${GITHUB_RUN_ID:-local}-$$"
WORKFLOW_NAME=""
TARGET_DIGEST=""
if [[ "$MODE" == oci ]]; then TARGET_DIGEST=${APP_REF#*@}; fi
finish() {
  rc=$?
  if [[ $rc -ne 0 ]]; then
    {
      kubectl get all,workflows,events -A -o wide || true
      kubectl get events -A --sort-by=.lastTimestamp || true
      kubectl get pods -n default -o name | while read -r pod; do
        kubectl logs -n default "$pod" --all-containers=true --tail=200 || true
      done
      if [[ -n "$WORKFLOW_NAME" ]]; then argo get "$WORKFLOW_NAME" -n default || true; argo logs "$WORKFLOW_NAME" -n default || true; fi
      kind export logs "$WORK/kind-logs" --name "$CLUSTER" || true
    } > "$ROOT/diagnostics/runtime-smoke.txt" 2>&1
  fi
  if [[ -n "$WORKFLOW_NAME" ]]; then
    argo get "$WORKFLOW_NAME" -n default -o json > "$ROOT/evidence/argo-workflow.json" 2>/dev/null || true
  fi
  jq -n --arg lane runtime-smoke --arg status "$([[ $rc -eq 0 ]] && echo passed || echo failed)" \
    --arg app "$APP" --arg mode "$MODE" --arg profile "$PROFILE" --arg sourceSha "$SOURCE_SHA" \
    --arg targetAdapter "$ADAPTER" --arg targetComponent "$TARGET" --arg targetVersion "$TARGET_VERSION" --arg targetDigest "$TARGET_DIGEST" \
    --arg evidenceScope "$EVIDENCE_SCOPE" --argjson fixtureOnly "$FIXTURE_ONLY" \
    --argjson executableProfiles "$EXECUTABLE_PROFILES" --argjson appEvidenceEligible "$APP_EVIDENCE_ELIGIBLE" \
    '{schema:"inari.lane-result.v1",lane:$lane,status:$status,app:$app,mode:$mode,profile:$profile,sourceSha:$sourceSha,targetAdapter:$targetAdapter,targetComponent:$targetComponent,targetVersion:$targetVersion,targetDigest:$targetDigest,fixtureOnly:$fixtureOnly,executableProfiles:$executableProfiles,evidenceScope:$evidenceScope,appEvidenceEligible:$appEvidenceEligible}' > "$ROOT/evidence/runtime-smoke.json"
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
  case "$ADAPTER" in
    helm)
      python3 "$LIBRARY/scripts/chart-test-config.py" --root "$ROOT" --chart "$CHART" > "$WORK/chart-test.json"
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
      helm upgrade --install "$APP" "$ROOT/$CHART" --namespace default \
        --values "$SUITE_DIR/values.yaml" --wait --timeout 5m
      ;;
    manifests)
      kubectl apply -R -f "$SUITE_DIR/$MANIFEST_PATH"
      ;;
  esac
else
  [[ "$WORKFLOW_SHA" =~ ^[0-9a-fA-F]{40}$ ]] || { echo "OCI mode requires the resolved workflow SHA" >&2; exit 2; }
  [[ "${GITHUB_REPOSITORY:-}" =~ ^[^/]+/[^/]+$ ]] || { echo "OCI mode requires the source repository" >&2; exit 2; }
  SOURCE_SHA=$(git -C "$ROOT" rev-parse HEAD)
  if [[ "$ADAPTER" == helm ]]; then
    APP_NAME=$(jq -r --arg target "$TARGET" 'first(.components[] | select(.kind == "chart" and .path == $target) | .name) // empty' "$ROOT/evidence-runtime-plan.json")
    APP_VERSION=$(jq -r --arg target "$TARGET" 'first(.components[] | select(.kind == "chart" and .path == $target) | .version) // empty' "$ROOT/evidence-runtime-plan.json")
    app_workflow_path=.github/workflows/release-chart.yml
    app_expected_publisher="^https://github\\.com/7K-Hiroba/workflows/\\.github/workflows/release-chart\\.yml@${WORKFLOW_SHA}$"
    app_media_type=application/vnd.cncf.helm.chart.v1
    app_required="validate chart"
  else
    APP_NAME=$(jq -r --arg target "$TARGET" 'first(.components[] | select(.kind == "package" and .path == $target) | .name) // empty' "$ROOT/evidence-runtime-plan.json")
    APP_VERSION=$(jq -r --arg target "$TARGET" 'first(.components[] | select(.kind == "package" and .path == $target) | .version) // empty' "$ROOT/evidence-runtime-plan.json")
    [[ -n "$APP_NAME" && -n "$APP_VERSION" && -n "$ARTIFACT_PATH" ]] || { echo "OCI manifests smoke requires an artifact-bound package and adapter.artifactPath" >&2; exit 2; }
    app_workflow_path=.github/workflows/release-oci.yml
    app_expected_publisher="^https://github\\.com/7K-Hiroba/workflows/\\.github/workflows/release-oci\\.yml@${WORKFLOW_SHA}$"
    app_media_type=application/vnd.inari.catalog.package.v1+yaml
    app_required="validate package"
  fi
  app_release_tag="$APP_NAME-v$APP_VERSION"
  for ref in "$APP_REF" "$SUITE_REF"; do
    repository=${ref%@*}
    if [[ "$ref" == "$APP_REF" ]]; then
      workflow_path=$app_workflow_path
      expected_publisher=$app_expected_publisher
      media_type=$app_media_type
      required=$app_required
      release_tag=$app_release_tag
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
  if [[ "$ADAPTER" == helm ]]; then
    APP_REPOSITORY=${APP_REF%@*}
    crane digest "$APP_REPOSITORY:$APP_VERSION" | grep -Fx "${APP_REF#*@}"
    helm upgrade --install "$APP" "oci://$APP_REPOSITORY" --namespace default --version "$APP_VERSION" --wait --timeout 5m
    crane digest "$APP_REPOSITORY:$APP_VERSION" | grep -Fx "${APP_REF#*@}"
  else
    mkdir -p "$WORK/app"
    oras pull --plain-http=false --output "$WORK/app" "$APP_REF"
    ARTIFACT_ROOT=$(python3 -c 'import sys; from pathlib import Path; sys.path.insert(0,sys.argv[2]); from lib.paths import confined_path; print(confined_path(Path(sys.argv[1]), sys.argv[3], "adapter.artifactPath"))' "$WORK/app" "$LIBRARY/scripts" "$ARTIFACT_PATH")
    if [[ -d "$ARTIFACT_ROOT" ]]; then
      kubectl apply -R -f "$ARTIFACT_ROOT"
    else
      kubectl apply -f "$ARTIFACT_ROOT"
    fi
  fi
fi
if [[ "$HAS_ADAPTER" == true ]]; then
  while IFS=$'\t' read -r kind name namespace condition; do
    [[ -n "$kind" ]] || continue
    kubectl wait --for=condition="$condition" "$kind/$name" --namespace "$namespace" --timeout 120s
  done < <(python3 -c 'import sys,yaml; target=yaml.safe_load(open(sys.argv[1]))["target"]; [print("{}\t{}\t{}\t{}".format(item["kind"], item["name"], item["namespace"], item["condition"])) for item in target["adapter"]["readiness"]]' "$SUITE_DIR/suite.yaml")
else
  kubectl wait --for=condition=Available deployment -l "app.kubernetes.io/name=$APP" --namespace default --timeout 120s
fi
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
TEMPLATE_NAME=$(python3 -c 'import sys,yaml; print(yaml.safe_load(open(sys.argv[1]))["metadata"]["name"])' "$SUITE_DIR/$WORKFLOW_FILE")
kubectl apply -f "$SUITE_DIR/$WORKFLOW_FILE"
argo lint "$SUITE_DIR/$WORKFLOW_FILE"
WORKFLOW_NAME=$(argo submit --from "workflowtemplate/$TEMPLATE_NAME" --namespace default -o name)
TIMEOUT=$(python3 -c 'import sys,yaml; print(yaml.safe_load(open(sys.argv[1]))["timeout"])' "$SUITE_DIR/suite.yaml")
timeout "$TIMEOUT" argo wait "$WORKFLOW_NAME" --namespace default
argo get "$WORKFLOW_NAME" --namespace default -o json | jq -e '.status.phase == "Succeeded"' >/dev/null
