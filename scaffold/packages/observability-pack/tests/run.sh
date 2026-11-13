#!/usr/bin/env bash
set -euo pipefail
PACKAGE_DIR=$(cd "$(dirname "$0")/.." && pwd)
kubectl apply -f "$PACKAGE_DIR/tests/deps/prometheusrule-crd.yaml"
kubectl apply -f "$PACKAGE_DIR/rgd.yaml"
kubectl wait --for=condition=Ready rgd/workflows-scaffold-observability --timeout=120s
kubectl apply -f "$PACKAGE_DIR/tests/fixture.yaml"
for _ in $(seq 1 60); do
  if kubectl get configmap workflows-scaffold-overview -n default >/dev/null 2>&1; then
    break
  fi
  sleep 2
done
kubectl get configmap workflows-scaffold-overview -n default
kubectl get configmap workflows-scaffold-folder -n default
kubectl get prometheusrule workflows-scaffold-central -n default
