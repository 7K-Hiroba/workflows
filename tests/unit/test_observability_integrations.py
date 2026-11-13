from __future__ import annotations

import json
import subprocess
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
PYTHON = ROOT / ".venv" / "bin" / "python"
if not PYTHON.exists():
    PYTHON = Path("python3")


class DeriveCentralFixtureTests(unittest.TestCase):
    def test_derives_labels_without_mutating_base_test(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = root / "base.yaml"
            base.write_text("rule_files: [rules/app.yaml]\ntests:\n  - input_series:\n      - series: 'workflows_scaffold_up{job=\"workflows-scaffold\"}'\n")
            actual = root / "actual.json"
            actual.write_text(json.dumps({"labels": {"cluster": "kind-ci", "job": "workflows-scaffold", "org": "ci"}, "value": 1}))
            output = root / "derived.yaml"
            result = subprocess.run([str(PYTHON), str(ROOT / "scripts/derive-central-rule-test.py"), "--base", str(base), "--actual", str(actual), "--rules", str(root / "rules/app.yaml"), "--output", str(output)], text=True, capture_output=True, check=False)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            derived = yaml.safe_load(output.read_text())
            series = derived["tests"][0]["input_series"][0]["series"]
            self.assertIn('org="ci"', series)
            self.assertIn('cluster="kind-ci"', series)
            self.assertEqual(derived["rule_files"], [str(root / "rules/app.yaml")])
            self.assertIn("rules/app.yaml", base.read_text())


class GrafanaHandler(BaseHTTPRequestHandler):
    fail_query = False
    missing_dashboard = False

    def send_json(self, value, status=200) -> None:
        body = json.dumps(value).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/api/health":
            self.send_json({"database": "ok"})
        elif self.path.startswith("/api/search"):
            self.send_json([] if self.missing_dashboard else [{"uid": "workflows-scaffold-overview", "title": "Overview", "folderTitle": "workflows-scaffold"}])
        elif self.path == "/api/dashboards/uid/workflows-scaffold-overview":
            self.send_json({"dashboard": {"uid": "workflows-scaffold-overview", "panels": [{"datasource": {"uid": "${DS_PROMETHEUS}"}, "targets": [{"expr": "workflows_scaffold_up"}]}], "templating": {"list": [{"name": "DS_PROMETHEUS", "current": {"value": "prometheus"}}]}}})
        elif self.path == "/api/datasources/uid/prometheus":
            self.send_json({"uid": "prometheus", "type": "prometheus"})
        else:
            self.send_json({"message": "not found"}, 404)

    def do_POST(self) -> None:  # noqa: N802
        if self.path == "/api/ds/query":
            self.send_json({"results": {"A": {"status": 500 if self.fail_query else 200, "frames": [] if self.fail_query else [{"data": [1]}]}}})
        else:
            self.send_json({"message": "not found"}, 404)

    def log_message(self, *args) -> None:
        return


class GrafanaCheckTests(unittest.TestCase):
    def setUp(self) -> None:
        GrafanaHandler.fail_query = False
        GrafanaHandler.missing_dashboard = False
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), GrafanaHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f"http://127.0.0.1:{self.server.server_port}"

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def run_check(self) -> subprocess.CompletedProcess[str]:
        return subprocess.run([str(PYTHON), str(ROOT / "scripts/check-grafana.py"), "--url", self.url, "--uid", "workflows-scaffold-overview", "--app", "workflows-scaffold"], text=True, capture_output=True, check=False)

    def test_ready_dashboard_and_query_pass(self) -> None:
        result = self.run_check()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_missing_dashboard_fails(self) -> None:
        GrafanaHandler.missing_dashboard = True
        result = self.run_check()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("dashboard", (result.stdout + result.stderr).lower())

    def test_failed_panel_query_fails(self) -> None:
        GrafanaHandler.fail_query = True
        result = self.run_check()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("query", (result.stdout + result.stderr).lower())


if __name__ == "__main__":
    unittest.main()
