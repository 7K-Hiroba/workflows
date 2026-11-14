#!/usr/bin/env bash
set -euo pipefail
PACKAGE_DIR=$(cd "$(dirname "$0")/.." && pwd)
kubectl create namespace policy-test --dry-run=client -o yaml | kubectl apply -f -
kubectl label namespace policy-test policy.test=workflows-scaffold --overwrite
kubectl apply -f "$PACKAGE_DIR/policies.yaml"
sleep 2
if kubectl apply -f "$PACKAGE_DIR/tests/deny.yaml"; then
  echo "unlabeled pod was unexpectedly admitted" >&2
  exit 1
fi
kubectl apply -f "$PACKAGE_DIR/tests/allow.yaml"
kubectl get pod allowed -n policy-test
