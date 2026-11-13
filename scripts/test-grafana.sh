#!/usr/bin/env bash
set -euo pipefail
ROOT=""
while [[ $# -gt 0 ]]; do
  case "$1" in --root) ROOT=$2; shift 2 ;; *) echo "unknown argument $1" >&2; exit 2 ;; esac
done
[[ -d "$ROOT" ]] || { echo "--root is required" >&2; exit 2; }
ROOT=$(cd "$ROOT" && pwd)
LIBRARY=$(cd "$(dirname "$0")/.." && pwd)
APP=$(python3 -c 'import sys,yaml; print(yaml.safe_load(open(sys.argv[1]))["app"])' "$ROOT/.hiroba.yaml")
WORK=$(mktemp -d)
SUFFIX=$$
NETWORK="hiroba-grafana-$SUFFIX"
FIXTURE="hiroba-grafana-fixture-$SUFFIX"
PROMETHEUS="hiroba-grafana-prometheus-$SUFFIX"
GRAFANA="hiroba-grafana-$SUFFIX"
mkdir -p "$WORK/dashboards" "$WORK/provisioning/datasources" "$WORK/provisioning/dashboards" "$ROOT/evidence" "$ROOT/diagnostics"
finish() {
  rc=$?
  if [[ $rc -ne 0 ]]; then
    {
      docker logs "$GRAFANA" || true
      docker logs "$PROMETHEUS" || true
    } > "$ROOT/diagnostics/grafana.txt" 2>&1
  fi
  docker rm -f "$GRAFANA" "$PROMETHEUS" "$FIXTURE" >/dev/null 2>&1 || true
  docker network rm "$NETWORK" >/dev/null 2>&1 || true
  rm -rf "$WORK"
  exit "$rc"
}
trap finish EXIT
cp "$ROOT/observability/dashboards/"*.json "$WORK/dashboards/"
cat > "$WORK/prometheus.yaml" <<'YAML'
global:
  scrape_interval: 1s
scrape_configs:
  - job_name: workflows-scaffold
    honor_labels: true
    static_configs:
      - targets: [fixture:80]
YAML
cat > "$WORK/provisioning/datasources/prometheus.yaml" <<'YAML'
apiVersion: 1
datasources:
  - name: Prometheus
    uid: prometheus
    type: prometheus
    access: proxy
    url: http://prometheus:9090
    isDefault: true
YAML
cat > "$WORK/provisioning/dashboards/hiroba.yaml" <<'YAML'
apiVersion: 1
providers:
  - name: hiroba
    folder: workflows-scaffold
    type: file
    options:
      path: /var/lib/grafana/dashboards
YAML
NGINX='nginx:1.29.3-alpine@sha256:667473807103639a0aca5b49534a216d2b64f0fb868aaa801f023da0cdd781c7'
PROM_IMAGE='prom/prometheus:v3.5.0@sha256:8672a850efe2f9874702406c8318704edb363587f8c2ca88586b4c8fdb5cea24'
GRAFANA_IMAGE='grafana/grafana:12.2.1@sha256:aa42cb1d973fc3d10609cd579455470f7255c535c9d3c3059c390c583709c14a'
docker network create "$NETWORK" >/dev/null
docker run -d --name "$FIXTURE" --network "$NETWORK" --network-alias fixture \
  -v "$ROOT/observability/tests/alloy/input.prom:/usr/share/nginx/html/metrics:ro" "$NGINX" >/dev/null
docker run -d --name "$PROMETHEUS" --network "$NETWORK" --network-alias prometheus \
  -v "$WORK/prometheus.yaml:/etc/prometheus/prometheus.yml:ro" "$PROM_IMAGE" >/dev/null
docker run -d --name "$GRAFANA" --network "$NETWORK" -p 127.0.0.1::3000 \
  -e GF_AUTH_ANONYMOUS_ENABLED=true -e GF_AUTH_ANONYMOUS_ORG_ROLE=Admin \
  -e GF_USERS_ALLOW_SIGN_UP=false -e GF_ANALYTICS_REPORTING_ENABLED=false \
  -v "$WORK/provisioning:/etc/grafana/provisioning:ro" \
  -v "$WORK/dashboards:/var/lib/grafana/dashboards:ro" \
  "$GRAFANA_IMAGE" >/dev/null
PORT=$(docker port "$GRAFANA" 3000/tcp | sed -n 's/.*://p' | head -n 1)
export GRAFANA_URL="http://127.0.0.1:$PORT"
python3 - <<'PY'
import os, time, urllib.request
for _ in range(60):
    try:
        with urllib.request.urlopen(os.environ["GRAFANA_URL"] + "/api/health", timeout=3) as response:
            if response.status == 200:
                break
    except Exception:
        pass
    time.sleep(1)
else:
    raise SystemExit("ephemeral Grafana did not become ready")
PY
while read -r uid; do
  [[ -n "$uid" ]] || continue
  passed=false
  for attempt in $(seq 1 30); do
    if python3 "$LIBRARY/scripts/check-grafana.py" --url "$GRAFANA_URL" --uid "$uid" --app "$APP"; then
      passed=true
      break
    fi
    sleep 1
  done
  [[ "$passed" == true ]] || { echo "Grafana dashboard $uid did not become query-ready" >&2; exit 1; }
done < <(python3 -c 'import sys,yaml; data=yaml.safe_load(open(sys.argv[1])); print("\n".join(item["uid"] for item in data["dashboards"]))' "$ROOT/observability/observability.yaml")
jq -n --arg app "$APP" '{schema:"inari.lane-result.v1",lane:"grafana",status:"passed",app:$app}' > "$ROOT/evidence/grafana.json"
