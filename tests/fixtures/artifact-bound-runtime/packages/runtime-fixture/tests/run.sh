#!/usr/bin/env bash
set -euo pipefail
PACKAGE_DIR=$(cd "$(dirname "$0")/.." && pwd)
python3 - "$PACKAGE_DIR/manifests.yaml" <<'PY'
import sys
import yaml
items = list(yaml.safe_load_all(open(sys.argv[1])))
assert [item["kind"] for item in items] == ["Deployment", "Service"]
assert "@sha256:" in items[0]["spec"]["template"]["spec"]["containers"][0]["image"]
PY
