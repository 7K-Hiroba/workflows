from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SHA = "a" * 40


class CompatEvidenceTests(unittest.TestCase):
    def test_backend_matrix_runs_and_writes_report(self) -> None:
        result = subprocess.run(
            ["bash", str(ROOT / "scripts/run-compat-backend.sh"), "--root", str(ROOT / "scaffold"), "--mode", "pr"],
            text=True,
            capture_output=True,
            check=False,
            env={"PATH": "/usr/local/go/bin:/usr/bin:/bin", "HOME": str(Path.home()), "SOURCE_SHA": SHA, "GOCACHE": "/tmp/go-cache", "GOMODCACHE": str(Path.home() / "go/pkg/mod"), "HIROBA_PYTHON": str(ROOT / ".venv/bin/python")},
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        report = ROOT / "scaffold/evidence/compat-report.json"
        data = json.loads(report.read_text())
        self.assertEqual(data["sourceSha"], SHA)
        self.assertEqual(data["status"], "passed")
        self.assertEqual(len(data["entries"]), 2)
        self.assertTrue(all(entry["status"] == "passed" for entry in data["entries"]))
        self.assertEqual([entry["pluginSdk"] for entry in data["entries"]], ["v1.2.1-ffb897b", "v1.2.0"])
        self.assertEqual(len({entry["pluginSdkSha"] for entry in data["entries"]}), 2)
        self.assertTrue(all(entry["testkit"] == "Info/Capabilities/Invoke/Health" for entry in data["entries"]))

    def test_backend_rejects_undeclared_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "ci").mkdir()
            (root / "ci/compatibility-matrix.json").write_text(json.dumps({"schema": "inari.compat.v1", "entries": [{"server": "stable", "ui": "stable", "pluginContracts": ["inari.plugin.v2"], "uiHostApis": ["inari.ui.v1"]}, {"server": "previous", "ui": "previous", "pluginContracts": ["inari.plugin.v2"], "uiHostApis": ["inari.ui.v1"]}]}))
            (root / "extension.yaml").write_text("spec:\n  contracts:\n    backend: [inari.plugin.v1]\n    ui: {hostApi: inari.ui.v1}\n")
            result = subprocess.run(["bash", str(ROOT / "scripts/run-compat-backend.sh"), "--root", str(root), "--mode", "pr"], text=True, capture_output=True, check=False, env={**os.environ, "HIROBA_PYTHON": str(ROOT / ".venv/bin/python"), "SOURCE_SHA": SHA})
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("inari.plugin.v1", result.stdout + result.stderr)

    def test_backend_rejects_sdk_tag_sha_mismatch_before_contract_claim(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "scaffold"
            shutil.copytree(ROOT / "scaffold", root, ignore=shutil.ignore_patterns("node_modules", "dist", "evidence", "diagnostics"))
            matrix = root / "ci/compatibility-matrix.json"
            data = json.loads(matrix.read_text())
            data["entries"][0]["pluginSdkSha"] = "0" * 40
            matrix.write_text(json.dumps(data))
            result = subprocess.run(["bash", str(ROOT / "scripts/run-compat-backend.sh"), "--root", str(root), "--mode", "pr"], text=True, capture_output=True, check=False, env={**os.environ, "HIROBA_PYTHON": str(ROOT / ".venv/bin/python"), "SOURCE_SHA": SHA})
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("SDK tag/SHA mismatch", result.stdout + result.stderr)

    def test_browser_report_requires_every_slot_and_walks_nested_suites(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            extension = root / "extension.yaml"
            extension.write_text("spec:\n  ui:\n    slots:\n      - {kind: cluster-tab, name: health}\n      - {kind: page, name: details}\n")
            report = root / "report.json"
            report.write_text(json.dumps({"suites": [{"specs": [{"title": "slot cluster-tab:health", "ok": True}], "suites": [{"specs": [{"title": "slot page:details", "ok": True}]}]}]}))
            result = subprocess.run([str(ROOT / ".venv/bin/python"), str(ROOT / "scripts/check-browser-report.py"), "--extension", str(extension), "--report", str(report)], text=True, capture_output=True, check=False)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            report.write_text(json.dumps({"suites": [{"specs": [{"title": "slot cluster-tab:health", "ok": True}]}]}))
            result = subprocess.run([str(ROOT / ".venv/bin/python"), str(ROOT / "scripts/check-browser-report.py"), "--extension", str(extension), "--report", str(report)], text=True, capture_output=True, check=False)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("page:details", result.stdout + result.stderr)

    def test_report_freshness_and_source_binding(self) -> None:
        now = datetime.now(timezone.utc)
        with tempfile.TemporaryDirectory() as tmp:
            report = Path(tmp) / "report.json"
            base = {"status": "passed", "sourceSha": SHA, "completedAt": now.isoformat().replace("+00:00", "Z"), "entries": [{"status": "passed"}]}
            for name, mutate, expected in (
                ("valid", lambda data: data, 0),
                ("stale", lambda data: data.update(completedAt=(now - timedelta(days=8)).isoformat().replace("+00:00", "Z")), 1),
                ("wrong-source", lambda data: data.update(sourceSha="b" * 40), 1),
                ("failed", lambda data: data.update(status="failed"), 1),
            ):
                with self.subTest(name=name):
                    data = dict(base)
                    mutate(data)
                    report.write_text(json.dumps(data))
                    result = subprocess.run(["python3", str(ROOT / "scripts/check-compat-report.py"), "--report", str(report), "--source-sha", SHA], text=True, capture_output=True, check=False)
                    self.assertEqual(result.returncode, expected, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
