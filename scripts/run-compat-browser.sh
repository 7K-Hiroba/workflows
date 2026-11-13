#!/usr/bin/env bash
set -euo pipefail
ROOT=""
MODE="pr"
while [[ $# -gt 0 ]]; do
  case "$1" in --root) ROOT=$2; shift 2 ;; --mode) MODE=$2; shift 2 ;; *) echo "unknown argument $1" >&2; exit 2 ;; esac
done
[[ "$MODE" == pr || "$MODE" == release || "$MODE" == nightly ]] || { echo "invalid compat mode" >&2; exit 2; }
ROOT=$(cd "$ROOT" && pwd)
LIBRARY=$(cd "$(dirname "$0")/.." && pwd)
MATRIX="$ROOT/ci/compatibility-matrix.json"
if [[ "$MODE" == nightly ]]; then
  HOST_SHA=$(gh api repos/7K-Inari/inari-ui/commits/main --jq '.sha')
else
  HOST_SHA=$(jq -r '.entries[0].uiHostSha // empty' "$MATRIX")
fi
[[ "$HOST_SHA" =~ ^[0-9a-f]{40}$ ]] || { echo "stable UI host must resolve to a full commit SHA" >&2; exit 2; }
[[ -f "$ROOT/ui/dist/remoteEntry.js" ]] || { echo "canonical UI build did not produce dist/remoteEntry.js" >&2; exit 2; }
mkdir -p "$ROOT/evidence" "$ROOT/diagnostics"
WORK=$(mktemp -d)
HOST_PID=""
REMOTE_PID=""
finish() {
  rc=$?
  [[ -n "$HOST_PID" ]] && kill "$HOST_PID" >/dev/null 2>&1 || true
  [[ -n "$REMOTE_PID" ]] && kill "$REMOTE_PID" >/dev/null 2>&1 || true
  jq -n --arg status "$([[ $rc -eq 0 ]] && echo passed || echo failed)" --arg sha "$HOST_SHA" \
    '{schema:"inari.browser-report.v1",status:$status,uiHostSha:$sha}' > "$ROOT/evidence/browser-report.json"
  rm -rf "$WORK"
  exit "$rc"
}
trap finish EXIT
git clone --filter=blob:none https://github.com/7K-Inari/inari-ui.git "$WORK/host"
git -C "$WORK/host" checkout "$HOST_SHA"
npm ci --include=dev --ignore-scripts --prefix "$WORK/host"
(
  cd "$WORK/host"
  VITE_MOCK_API=true npm run dev -- --host 127.0.0.1 --port 5173 > "$ROOT/diagnostics/ui-host.log" 2>&1
) &
HOST_PID=$!
python3 "$LIBRARY/scripts/serve-ui-remote.py" --directory "$ROOT/ui/dist" --port 8080 > "$ROOT/diagnostics/ui-remote.log" 2>&1 &
REMOTE_PID=$!
python3 - <<'PY'
import time, urllib.request
for url in ("http://127.0.0.1:5173", "http://127.0.0.1:8080/remoteEntry.js"):
    for _ in range(60):
        try:
            with urllib.request.urlopen(url, timeout=3) as response:
                if response.status == 200:
                    break
        except Exception:
            pass
        time.sleep(1)
    else:
        raise SystemExit(f"browser dependency did not become ready: {url}")
PY
cd "$ROOT/ui"
npx playwright install chromium
set +e
INARI_UI_URL=http://127.0.0.1:5173 INARI_REMOTE_ENTRY=http://127.0.0.1:8080/remoteEntry.js \
  npm run test:browser -- --reporter=json --output="$ROOT/evidence/playwright-artifacts" > "$ROOT/evidence/playwright-report.json"
RESULT=$?
set -e
[[ $RESULT -eq 0 ]] || exit "$RESULT"
python3 "$LIBRARY/scripts/check-browser-report.py" --extension "$ROOT/extension.yaml" --report "$ROOT/evidence/playwright-report.json"
