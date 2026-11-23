#!/usr/bin/env bash
set -euo pipefail
CHART=charts/workflows-scaffold
VERSION=$(helm show chart "$HIROBA_STACK_ROOT/$CHART" | awk '/^version:/ {print $2}')
mkdir -p "$HIROBA_STACK_WORK/current"
helm package "$HIROBA_STACK_ROOT/$CHART" --version "$VERSION" --destination "$HIROBA_STACK_WORK/current" >/dev/null
PACKAGE="$HIROBA_STACK_WORK/current/workflows-scaffold-$VERSION.tgz"
DIGEST=$(sha256sum "$PACKAGE" | awk '{print $1}')
helm upgrade --install workflows-scaffold "$PACKAGE" --namespace default \
  --values "$HIROBA_STACK_ROOT/$CHART/ci/kind-values.yaml" --wait --timeout 5m
bash "$HIROBA_STACK_ROOT/packages/observability-pack/tests/run.sh"
test "$(cat "$HIROBA_STACK_WORK/dashboard-uid")" = "$(kubectl get configmap workflows-scaffold-overview -n default -o jsonpath='{.metadata.uid}')"
jq -n --arg version "$VERSION" --arg digest "sha256:$DIGEST" \
  '{schema:"inari.stack-phase-result.v1",phase:"upgrade",version:$version,contentDigest:$digest,converged:true}' \
  > "$HIROBA_STACK_WORK/upgrade-result.json"
