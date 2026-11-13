#!/usr/bin/env bash
set -euo pipefail
ROOT=""
MODE=pr
while [[ $# -gt 0 ]]; do
  case "$1" in --root) ROOT=$2; shift 2 ;; --mode) MODE=$2; shift 2 ;; *) echo "unknown argument $1" >&2; exit 2 ;; esac
done
[[ "$MODE" == pr || "$MODE" == release || "$MODE" == nightly ]] || { echo "invalid compat mode" >&2; exit 2; }
ROOT=$(cd "$ROOT" && pwd)
cd "$ROOT"
PYTHON=${HIROBA_PYTHON:-python3}
MATRIX="$ROOT/ci/compatibility-matrix.json"
if [[ -f "$ROOT/.hiroba.yaml" ]]; then
  MATRIX="$ROOT/$($PYTHON -c 'import sys,yaml; print(yaml.safe_load(open(sys.argv[1]))["compatibility"]["matrix"])' "$ROOT/.hiroba.yaml")"
fi
COUNT=$(jq '.entries | length' "$MATRIX")
if [[ "$MODE" != nightly && "$COUNT" -lt 2 ]]; then
  echo "reviewed compat requires current stable and previous stable entries" >&2
  exit 2
fi
mkdir -p "$ROOT/evidence"
RESULTS=$(mktemp)
trap 'rm -f "$RESULTS"' EXIT
STATUS=passed
INDEX=0
while read -r ENTRY; do
  export ENTRY
  if ! "$PYTHON" - <<'PY'
import json, os, sys, yaml
entry = json.loads(os.environ["ENTRY"])
manifest = yaml.safe_load(open("extension.yaml"))
contracts = manifest.get("spec", {}).get("contracts", {})
missing = [item for item in contracts.get("backend", []) if item not in entry.get("pluginContracts", [])]
ui = contracts.get("ui", {})
if ui.get("hostApi") not in entry.get("uiHostApis", []):
    missing.append(ui.get("hostApi"))
if missing:
    print(f"unsupported contracts {missing} for {entry}", file=sys.stderr)
    sys.exit(1)
PY
  then
    STATUS=failed
  fi
  export INARI_COMPAT_INDEX="$INDEX"
  if [[ "$STATUS" == passed ]]; then
    if ! (cd extension && go test -json ./...) > "$ROOT/evidence/compat-$INDEX.json"; then STATUS=failed; fi
  fi
  jq -c --argjson entry "$ENTRY" --arg status "$STATUS" '{server:$entry.server,ui:$entry.ui,uiHostSha:($entry.uiHostSha // null),status:$status}' <<< "$ENTRY" >> "$RESULTS"
  INDEX=$((INDEX + 1))
  [[ "$STATUS" == passed ]] || break
done < <(jq -c '.entries[]' "$MATRIX")
SOURCE_SHA=${SOURCE_SHA:-$(git -C "$ROOT" rev-parse HEAD)}
export SOURCE_SHA MODE STATUS RESULTS MATRIX
if [[ "$MODE" == nightly ]]; then
  SERVER_EDGE=$(gh api repos/7K-Inari/inari-server/commits/main --jq '.sha')
  UI_EDGE=$(gh api repos/7K-Inari/inari-ui/commits/main --jq '.sha')
  export SERVER_EDGE UI_EDGE
fi
"$PYTHON" - <<'PY'
import json, os
from datetime import datetime, timezone
entries = [json.loads(line) for line in open(os.environ["RESULTS"]) if line.strip()]
report = {
    "schema": "inari.compat-report.v1",
    "mode": os.environ["MODE"],
    "sourceSha": os.environ["SOURCE_SHA"],
    "completedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    "status": os.environ["STATUS"],
    "entries": entries,
}
if os.environ["MODE"] == "nightly":
    report["resolvedEdge"] = {"serverSha": os.environ["SERVER_EDGE"], "uiSha": os.environ["UI_EDGE"]}
with open("evidence/compat-report.json", "w") as handle:
    json.dump(report, handle, indent=2, sort_keys=True)
    handle.write("\n")
PY
[[ "$STATUS" == passed ]]
