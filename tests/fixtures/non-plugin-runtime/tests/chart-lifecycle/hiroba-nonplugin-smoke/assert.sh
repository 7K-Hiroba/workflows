#!/usr/bin/env bash
set -euo pipefail

release=$HIROBA_CHART_RELEASE
namespace=$HIROBA_CHART_NAMESPACE
marker=$(kubectl get configmap "$release-lifecycle" --namespace "$namespace" -o jsonpath='{.data.phase}')
actual_digest="sha256:$(sha256sum "$HIROBA_CHART_PACKAGE" | awk '{print $1}')"
[[ "$actual_digest" == "$HIROBA_CHART_DIGEST" ]] || { echo "phase package digest differs from its declared evidence identity" >&2; exit 1; }
kubectl get service "$release" --namespace "$namespace" >/dev/null

case "$HIROBA_CHART_PHASE" in
  install)
    [[ "$marker" == previous ]] || { echo "install did not converge to previous content" >&2; exit 1; }
    if kubectl get deployment "$release" --namespace "$namespace" >/dev/null 2>&1; then
      echo "previous package unexpectedly contains the current Deployment" >&2
      exit 1
    fi
    kubectl get service "$release" --namespace "$namespace" -o jsonpath='{.metadata.uid}' > "$HIROBA_CHART_WORK/previous-service-uid"
    ;;
  upgrade)
    [[ "$marker" == current ]] || { echo "upgrade did not converge to current content" >&2; exit 1; }
    kubectl wait --for=condition=Available "deployment/$release" --namespace "$namespace" --timeout=120s
    current_uid=$(kubectl get service "$release" --namespace "$namespace" -o jsonpath='{.metadata.uid}')
    [[ "$current_uid" == "$(cat "$HIROBA_CHART_WORK/previous-service-uid")" ]] || { echo "upgrade replaced the stable Service identity" >&2; exit 1; }
    ;;
  *) echo "unknown lifecycle assertion phase" >&2; exit 2 ;;
esac
