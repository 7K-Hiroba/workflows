#!/usr/bin/env bash
set -euo pipefail
ROOT=""
while [[ $# -gt 0 ]]; do
  case "$1" in --root) ROOT=$2; shift 2 ;; *) echo "unknown argument $1" >&2; exit 2 ;; esac
done
[[ -d "$ROOT" ]] || { echo "--root is required" >&2; exit 2; }
ROOT=$(cd "$ROOT" && pwd)
LIBRARY=$(cd "$(dirname "$0")/.." && pwd)
ALLOY_DIR="$ROOT/observability/tests/alloy"
WORK=$(mktemp -d)
SUFFIX=$$
NETWORK="hiroba-alloy-$SUFFIX"
FIXTURE="hiroba-alloy-fixture-$SUFFIX"
PROMETHEUS="hiroba-alloy-prometheus-$SUFFIX"
ALLOY="hiroba-alloy-$SUFFIX"
mkdir -p "$ROOT/evidence" "$ROOT/diagnostics"
finish() {
  rc=$?
  if [[ $rc -ne 0 ]]; then
    {
      docker logs "$ALLOY" || true
      docker logs "$PROMETHEUS" || true
      docker logs "$FIXTURE" || true
    } > "$ROOT/diagnostics/alloy.txt" 2>&1
  fi
  docker rm -f "$ALLOY" "$PROMETHEUS" "$FIXTURE" >/dev/null 2>&1 || true
  docker network rm "$NETWORK" >/dev/null 2>&1 || true
  rm -rf "$WORK"
  exit "$rc"
}
trap finish EXIT
sed -e 's/__TARGET__/fixture:80/g' -e 's#__REMOTE_WRITE_URL__#http://prometheus:9090/api/v1/write#g' \
  "$ALLOY_DIR/config.river" > "$WORK/config.river"
printf 'global: {}\n' > "$WORK/prometheus.yml"
docker network create "$NETWORK" >/dev/null
NGINX='nginx:1.29.3-alpine@sha256:667473807103639a0aca5b49534a216d2b64f0fb868aaa801f023da0cdd781c7'
PROM_IMAGE='prom/prometheus:v3.5.0@sha256:8672a850efe2f9874702406c8318704edb363587f8c2ca88586b4c8fdb5cea24'
ALLOY_IMAGE='grafana/alloy:v1.13.0@sha256:d0621fba0c76cea5be5eb7e327580feb229763740b213fe237b30e0bb07ec184'
docker run -d --name "$FIXTURE" --network "$NETWORK" --network-alias fixture \
  -v "$ALLOY_DIR/input.prom:/usr/share/nginx/html/metrics:ro" "$NGINX" >/dev/null
docker run -d --name "$PROMETHEUS" --network "$NETWORK" --network-alias prometheus \
  -v "$WORK:/prometheus:ro" \
  -p 127.0.0.1::9090 "$PROM_IMAGE" \
  --web.enable-remote-write-receiver --storage.tsdb.path=/tmp/prometheus >/dev/null
docker run -d --name "$ALLOY" --network "$NETWORK" \
  -v "$WORK/config.river:/etc/alloy/config.river:ro" "$ALLOY_IMAGE" \
  run /etc/alloy/config.river --server.http.listen-addr=0.0.0.0:12345 --storage.path=/tmp/alloy >/dev/null
PORT=$(docker port "$PROMETHEUS" 9090/tcp | sed -n 's/.*://p' | head -n 1)
export PROM_PORT="$PORT"
export EXPECTED_FILE="$ALLOY_DIR/expected-central-series.json"
export ACTUAL_FILE="$WORK/actual.json"
python3 - <<'PY'
import json, os, time, urllib.parse, urllib.request
query = urllib.parse.urlencode({"query": "workflows_scaffold_up"})
url = f"http://127.0.0.1:{os.environ['PROM_PORT']}/api/v1/query?{query}"
last = None
for _ in range(60):
    try:
        with urllib.request.urlopen(url, timeout=3) as response:
            payload = json.load(response)
        result = payload.get("data", {}).get("result", [])
        if result:
            last = result[0]
            break
    except Exception as exc:
        last = {"error": str(exc)}
    time.sleep(1)
if not last or "metric" not in last:
    raise SystemExit(f"no post-Alloy series arrived: {last}")
labels = {key: value for key, value in last["metric"].items() if key != "__name__"}
value = float(last["value"][1])
actual = {"metric": "workflows_scaffold_up", "labels": labels, "value": value}
expected = json.load(open(os.environ["EXPECTED_FILE"]))
for key, value in expected["labels"].items():
    if labels.get(key) != value:
        raise SystemExit(f"label {key}: got {labels.get(key)!r}, want {value!r}; actual={labels}")
if actual["value"] != expected["value"]:
    raise SystemExit(f"value: got {actual['value']}, want {expected['value']}")
with open(os.environ["ACTUAL_FILE"], "w") as handle:
    json.dump(actual, handle, indent=2, sort_keys=True)
    handle.write("\n")
PY
cp "$WORK/actual.json" "$ROOT/evidence/alloy-central-series.json"
python3 "$LIBRARY/scripts/derive-central-rule-test.py" \
  --base "$ROOT/observability/tests/rules/app.test.yaml" \
  --actual "$WORK/actual.json" \
  --rules "$ROOT/observability/rules/app.yaml" \
  --output "$WORK/central.test.yaml"
promtool test rules "$WORK/central.test.yaml"
