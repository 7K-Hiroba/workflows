#!/usr/bin/env bash
set -euo pipefail
ROOT=""
MODE="pr"
while [[ $# -gt 0 ]]; do
  case "$1" in --root) ROOT=$2; shift 2 ;; --mode) MODE=$2; shift 2 ;; *) echo "unknown argument $1" >&2; exit 2 ;; esac
done
[[ "$MODE" == pr || "$MODE" == release || "$MODE" == nightly ]] || { echo "invalid compat mode" >&2; exit 2; }
ROOT=$(cd "$ROOT" && pwd)
cd "$ROOT"
LIBRARY=$(cd "$(dirname "$0")/.." && pwd)
PYTHON=${HIROBA_PYTHON:-python3}
MATRIX="$ROOT/ci/compatibility-matrix.json"
if [[ -f "$ROOT/.hiroba.yaml" ]]; then
  MATRIX="$ROOT/$($PYTHON -c 'import sys,yaml; from pathlib import Path; sys.path.insert(0,sys.argv[2]); from lib.paths import relative_path; data=yaml.safe_load(open(sys.argv[1])); print(relative_path(Path(sys.argv[3]), data["compatibility"]["matrix"], "compatibility.matrix"))' "$ROOT/.hiroba.yaml" "$LIBRARY/scripts" "$ROOT")"
fi
COUNT=$(jq '.entries | length' "$MATRIX")
if [[ "$MODE" != nightly && "$COUNT" -lt 2 ]]; then
  echo "reviewed compat requires current stable and previous stable entries" >&2
  exit 2
fi
# Resolve every nightly edge locator before any test executes.
if [[ "$MODE" == nightly ]]; then
  SERVER_EDGE=$(gh api repos/7K-Inari/inari-server/commits/main --jq '.sha')
  UI_EDGE=$(gh api repos/7K-Inari/inari-ui/commits/main --jq '.sha')
  SDK_EDGE=$(gh api repos/7K-Inari/inari-plugin-sdk/commits/main --jq '.sha')
  export SERVER_EDGE UI_EDGE SDK_EDGE
fi
mkdir -p "$ROOT/evidence"
RESULTS=$(mktemp)
ENTRIES=$(mktemp)
WORK=$(mktemp -d)
trap 'rm -f "$RESULTS" "$ENTRIES"; rm -rf "$WORK"' EXIT
jq -c '.entries[]' "$MATRIX" > "$ENTRIES"
if [[ "$MODE" == nightly ]]; then
  jq -c -n --arg server "$SERVER_EDGE" --arg ui "$UI_EDGE" --arg sdk "$SDK_EDGE" \
    '{server:$server,ui:$ui,uiHostSha:$ui,pluginSdk:$sdk,pluginSdkSha:$sdk,pluginContracts:["inari.plugin.v1"],uiHostApis:["inari.ui.v1"]}' >> "$ENTRIES"
fi
STATUS=passed
INDEX=0
while read -r ENTRY <&3; do
  export ENTRY
  ENTRY_STATUS=passed
  TESTKIT=""
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
    ENTRY_STATUS=failed
  fi
  SDK_VERSION=$(jq -r '.pluginSdk // empty' <<< "$ENTRY")
  SDK_SHA=$(jq -r '.pluginSdkSha // empty' <<< "$ENTRY")
  if [[ "$ENTRY_STATUS" == passed ]]; then
    if [[ "$SDK_VERSION" == "$SDK_SHA" && "$SDK_SHA" =~ ^[0-9a-f]{40}$ ]]; then
      RESOLVED_SDK=$SDK_SHA
    else
      RESOLVED_SDK=$(git ls-remote https://github.com/7K-Inari/inari-plugin-sdk.git "refs/tags/$SDK_VERSION" "refs/tags/$SDK_VERSION^{}" | awk 'END {print $1}')
    fi
    if [[ -z "$RESOLVED_SDK" || "$RESOLVED_SDK" != "$SDK_SHA" ]]; then
      echo "SDK tag/SHA mismatch for $SDK_VERSION: $RESOLVED_SDK != $SDK_SHA" >&2
      ENTRY_STATUS=failed
    fi
  fi
  if [[ "$ENTRY_STATUS" == passed ]]; then
    COPY="$WORK/entry-$INDEX"
    cp -R "$ROOT/extension" "$COPY"
    if ! (cd "$COPY" && go get "github.com/7K-Inari/inari-plugin-sdk@$SDK_VERSION" && go mod tidy) < /dev/null > "$ROOT/evidence/compat-$INDEX-module.log" 2>&1; then
      ENTRY_STATUS=failed
    elif ! grep -R 'inari-plugin-sdk/testkit' --include='*.go' "$COPY" >/dev/null || \
      ! grep -R '\.Info(' --include='*.go' "$COPY" >/dev/null || \
      ! grep -R '\.Capabilities(' --include='*.go' "$COPY" >/dev/null || \
      ! grep -R '\.Invoke(' --include='*.go' "$COPY" >/dev/null || \
      ! grep -R '\.Health(' --include='*.go' "$COPY" >/dev/null; then
      echo "extension tests must execute testkit Info/Capabilities/Invoke/Health" >&2
      ENTRY_STATUS=failed
    elif ! (cd "$COPY" && go test -count=1 -json ./...) < /dev/null > "$ROOT/evidence/compat-$INDEX.json"; then
      ENTRY_STATUS=failed
    else
      TESTKIT="Info/Capabilities/Invoke/Health"
    fi
  fi
  jq -c -n --argjson entry "$ENTRY" --arg status "$ENTRY_STATUS" --arg testkit "$TESTKIT" \
    '{server:$entry.server,ui:$entry.ui,uiHostSha:($entry.uiHostSha // null),pluginSdk:$entry.pluginSdk,pluginSdkSha:$entry.pluginSdkSha,status:$status,testkit:$testkit}' >> "$RESULTS"
  [[ "$ENTRY_STATUS" == passed ]] || STATUS=failed
  INDEX=$((INDEX + 1))
done 3< "$ENTRIES"
SOURCE_SHA=${SOURCE_SHA:-$(git -C "$ROOT" rev-parse HEAD)}
export SOURCE_SHA MODE STATUS RESULTS MATRIX
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
    report["resolvedEdge"] = {"serverSha": os.environ["SERVER_EDGE"], "uiSha": os.environ["UI_EDGE"], "pluginSdkSha": os.environ["SDK_EDGE"]}
with open("evidence/compat-report.json", "w") as handle:
    json.dump(report, handle, indent=2, sort_keys=True)
    handle.write("\n")
PY
[[ "$STATUS" == passed ]]
