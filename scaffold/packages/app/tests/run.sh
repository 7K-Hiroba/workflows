#!/usr/bin/env bash
set -euo pipefail
PACKAGE_DIR=$(cd "$(dirname "$0")/.." && pwd)
ROOT=$(cd "$PACKAGE_DIR/../.." && pwd)
CHART=${CHART_DIR:-$ROOT/charts/workflows-scaffold}
RENDERED=$(mktemp)
trap 'rm -f "$RENDERED"' EXIT
helm template workflows-scaffold "$CHART" --namespace workflows-scaffold --values "$PACKAGE_DIR/values-defaults.yaml" > "$RENDERED"
grep -q 'kind: Deployment' "$RENDERED"
grep -q 'kind: Service' "$RENDERED"
grep -q 'runAsNonRoot: true' "$RENDERED"
