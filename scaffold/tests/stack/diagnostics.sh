#!/usr/bin/env bash
set -euo pipefail
helm history workflows-scaffold --namespace default || true
kubectl get configmaps,prometheusrules -A -o yaml || true
