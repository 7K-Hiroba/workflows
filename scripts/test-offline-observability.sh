#!/usr/bin/env bash
set -euo pipefail
ROOT=""
while [[ $# -gt 0 ]]; do
  case "$1" in --root) ROOT=$2; shift 2 ;; *) echo "unknown argument $1" >&2; exit 2 ;; esac
done
[[ -d "$ROOT" ]] || { echo "--root is required" >&2; exit 2; }
ROOT=$(cd "$ROOT" && pwd)
LIBRARY=$(cd "$(dirname "$0")/.." && pwd)
PYTHON=${HIROBA_PYTHON:-python3}
ALLOY_CONFIG="$ROOT/$($PYTHON -c 'import sys,yaml; print(yaml.safe_load(open(sys.argv[1]))["observability"]["alloyConfig"])' "$ROOT/.hiroba.yaml")"
ALLOY_DIR=$(dirname "$ALLOY_CONFIG")
FIXTURE="$ALLOY_DIR/expected-central-series.json"
"$PYTHON" - "$FIXTURE" "$ALLOY_CONFIG" <<'PY'
import json, sys
fixture = json.load(open(sys.argv[1]))
if fixture.get("fixtureVersion") != "alloy-v1.13.0":
    raise SystemExit("fixtureVersion must match alloy-v1.13.0")
if fixture.get("reviewRequired") is not True:
    raise SystemExit("post-Alloy fixture must require CODEOWNERS review")
if fixture.get("sourceConfig") != "config.river":
    raise SystemExit("post-Alloy fixture must bind sourceConfig=config.river")
PY
mkdir -p "$ROOT/evidence" "$ROOT/diagnostics"
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT
alloy fmt --test "$ALLOY_CONFIG"
alloy validate --stability.level generally-available --feature.community-components.enabled=false "$ALLOY_CONFIG"
mkdir -p "$WORK/gcx"
"$PYTHON" - "$ROOT/observability/dashboards" "$WORK/gcx" <<'PY'
import json, sys
from pathlib import Path
source, output = Path(sys.argv[1]), Path(sys.argv[2])
for path in source.glob("*.json"):
    dashboard = json.loads(path.read_text())
    resource = {
        "kind": "Dashboard",
        "apiVersion": "dashboard.grafana.app/v1beta1",
        "metadata": {"name": dashboard["uid"], "annotations": {"inari.dev/dashboard-uid": dashboard["uid"]}},
        "spec": dashboard,
    }
    (output / path.name).write_text(json.dumps(resource, indent=2, sort_keys=True) + "\n")
PY
gcx dev lint run "$WORK/gcx" > "$WORK/gcx-output.jsonl"
cat "$WORK/gcx-output.jsonl"
"$PYTHON" - "$WORK/gcx-output.jsonl" <<'PY'
import json, sys
summaries = []
for line in open(sys.argv[1]):
    try:
        item = json.loads(line)
    except json.JSONDecodeError:
        continue
    if isinstance(item.get("summary"), dict):
        summaries.append(item["summary"])
if not summaries or not any(item.get("files_scanned", 0) > 0 for item in summaries):
    raise SystemExit("gcx scanned zero dashboard resources")
for summary in summaries:
    if summary.get("files_failed", 0) != 0 or summary.get("num_violations", 0) != 0:
        raise SystemExit(f"gcx dashboard lint failed: {summary}")
PY
for rules in "$ROOT"/observability/rules/*.yaml; do promtool check rules "$rules"; done
for test_file in "$ROOT"/observability/tests/rules/*.test.yaml; do promtool test rules "$test_file"; done
"$PYTHON" "$LIBRARY/scripts/derive-central-rule-test.py" \
  --base "$ROOT/observability/tests/rules/app.test.yaml" \
  --actual "$FIXTURE" \
  --rules "$ROOT/observability/rules/app.yaml" \
  --output "$WORK/central.test.yaml"
promtool test rules "$WORK/central.test.yaml"
jq -n --arg fixture "$FIXTURE" '{schema:"inari.lane-result.v1",lane:"offline-observability",status:"passed",fixture:$fixture,liveReadiness:"not-proven-offline"}' > "$ROOT/evidence/offline-observability.json"
