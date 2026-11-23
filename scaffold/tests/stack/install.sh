#!/usr/bin/env bash
set -euo pipefail
CHART=charts/workflows-scaffold
VERSION=$(helm show chart "$HIROBA_STACK_ROOT/$CHART" | awk '/^version:/ {print $2}')
PREVIOUS="$VERSION-ci.0"
mkdir -p "$HIROBA_STACK_WORK/previous"
python3 "$HIROBA_WORKFLOW_ROOT/scripts/prepare-chart.py" --chart "$HIROBA_STACK_ROOT/$CHART"
helm package "$HIROBA_STACK_ROOT/$CHART" --version "$PREVIOUS" --destination "$HIROBA_STACK_WORK/previous" >/dev/null
PACKAGE="$HIROBA_STACK_WORK/previous/workflows-scaffold-$PREVIOUS.tgz"
DIGEST=$(sha256sum "$PACKAGE" | awk '{print $1}')
python3 "$HIROBA_WORKFLOW_ROOT/scripts/chart-test-config.py" --root "$HIROBA_STACK_ROOT" --chart "$CHART" > "$HIROBA_STACK_WORK/chart-test.json"
if [[ $(jq -r '.image != null' "$HIROBA_STACK_WORK/chart-test.json") == true ]]; then
  repository=$(jq -r .image.repository "$HIROBA_STACK_WORK/chart-test.json")
  tag=$(jq -r .image.tag "$HIROBA_STACK_WORK/chart-test.json")
  context=$(jq -r .image.context "$HIROBA_STACK_WORK/chart-test.json")
  docker build -t "$repository:$tag" "$HIROBA_STACK_ROOT/$context"
  kind load docker-image "$repository:$tag" --name "$HIROBA_STACK_CLUSTER"
fi
while read -r dependency; do
  [[ -n "$dependency" ]] || continue
  kubectl apply -f "$HIROBA_STACK_ROOT/$dependency"
done < <(jq -r '.dependencies[]' "$HIROBA_STACK_WORK/chart-test.json")
helm upgrade --install workflows-scaffold "$PACKAGE" --namespace default \
  --values "$HIROBA_STACK_ROOT/$CHART/ci/kind-values.yaml" --wait --timeout 5m
bash "$HIROBA_STACK_ROOT/packages/observability-pack/tests/run.sh"
kubectl get configmap workflows-scaffold-overview -n default -o jsonpath='{.metadata.uid}' > "$HIROBA_STACK_WORK/dashboard-uid"
jq -n --arg version "$PREVIOUS" --arg digest "sha256:$DIGEST" \
  '{schema:"inari.stack-phase-result.v1",phase:"install",version:$version,contentDigest:$digest,converged:true}' \
  > "$HIROBA_STACK_WORK/install-result.json"
