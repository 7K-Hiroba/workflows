#!/usr/bin/env bash
set -euo pipefail

FIXTURE=$(cd "$(dirname "$0")" && pwd)
APP_ROOT=$(cd "$FIXTURE/../../.." && pwd)
LIBRARY=$(cd "$APP_ROOT/../../.." && pwd)
HELM=${HELM:?HELM must identify the checksum-verified pinned Helm binary}
PYTHON=${PYTHON:-python3}
EXPECTED_VERSION=$(jq -r .tools.helm.version "$LIBRARY/pins/stack-testing.json")
EXPECTED_ARCHIVE=$(jq -r .tools.helm.sha256 "$LIBRARY/pins/stack-testing.json")
ACTUAL_VERSION=$("$HELM" version --template '{{.Version}}')
ACTUAL_VERSION=${ACTUAL_VERSION#v}
[[ "$ACTUAL_VERSION" == "$EXPECTED_VERSION" ]] || { echo "Helm $EXPECTED_VERSION is required, found $ACTUAL_VERSION" >&2; exit 2; }
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT
cp -R "$FIXTURE/previous-chart" "$WORK/previous"
cp -R "$APP_ROOT/charts/hiroba-nonplugin-smoke" "$WORK/current"
find "$WORK/previous" "$WORK/current" -type f -exec touch -d '@0' {} +
mkdir "$WORK/previous-package" "$WORK/current-package"
"$HELM" package "$WORK/previous" --destination "$WORK/previous-package"
"$HELM" package "$WORK/current" --destination "$WORK/current-package"
PYTHONPATH="$LIBRARY/scripts" "$PYTHON" -m lib.chart_lifecycle canonicalize-package \
  --input "$WORK/previous-package/hiroba-nonplugin-smoke-0.0.9.tgz" --output "$FIXTURE/previous.tgz"
PYTHONPATH="$LIBRARY/scripts" "$PYTHON" -m lib.chart_lifecycle canonicalize-package \
  --input "$WORK/current-package/hiroba-nonplugin-smoke-0.1.0.tgz" --output "$FIXTURE/current.tgz"
"$PYTHON" - "$FIXTURE" "$EXPECTED_VERSION" "$EXPECTED_ARCHIVE" <<'PY'
import hashlib
import json
import sys
from pathlib import Path

fixture = Path(sys.argv[1])
packages = []
for phase, filename, version, source in (
    ("install", "previous.tgz", "0.0.9", "tests/chart-lifecycle/hiroba-nonplugin-smoke/previous-chart"),
    ("upgrade", "current.tgz", "0.1.0", "charts/hiroba-nonplugin-smoke"),
):
    digest = hashlib.sha256((fixture / filename).read_bytes()).hexdigest()
    packages.append({"phase": phase, "file": filename, "source": source, "chartVersion": version, "sha256": "sha256:" + digest})
document = {
    "schema": "inari.chart-lifecycle-fixture-provenance.v1",
    "generator": {
        "helmVersion": sys.argv[2],
        "helmArchiveSha256": sys.argv[3],
        "sourceFileMtimes": "unix-epoch",
        "archiveCanonicalization": "sorted members, normalized tar metadata, zero gzip mtime",
        "command": "PYTHON=<workflow-python> HELM=<checksum-verified-pinned-helm> ./generate.sh",
    },
    "packages": packages,
}
(fixture / "provenance.json").write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY
sha256sum "$FIXTURE/previous.tgz" "$FIXTURE/current.tgz"
