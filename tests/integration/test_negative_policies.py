from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PYTHON = ROOT / ".venv/bin/python"


class NegativePolicyIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "scaffold"
        shutil.copytree(ROOT / "scaffold", self.root, ignore=shutil.ignore_patterns("node_modules", "dist", "evidence", "diagnostics"))

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_generated_observability_drift_fails_without_write(self) -> None:
        target = self.root / "charts/workflows-scaffold/templates/observability/dashboards.yaml"
        target.write_text("# intentional drift\n")
        result = subprocess.run([str(PYTHON), str(ROOT / "scripts/render-observability.py"), "--root", str(self.root), "--check"], text=True, capture_output=True, check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(target.read_text(), "# intentional drift\n")

    def test_mutable_smoke_image_is_rejected(self) -> None:
        path = self.root / "tests/smoke/workflowtemplate.yaml"
        path.write_text(path.read_text().replace("curlimages/curl:8.11.1@sha256:9be9b39ac2a66b98bef6d1e1e615af8ff50ec2e746b9163bc12f2bdbf14a949d", "curlimages/curl:latest"))
        result = subprocess.run([str(PYTHON), str(ROOT / "scripts/validate-repository.py"), "--root", str(self.root)], text=True, capture_output=True, check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("digest", result.stdout + result.stderr)

    def test_mutable_workflow_ref_is_rejected(self) -> None:
        path = self.root / ".github/workflows/validate.yml.template"
        path.write_text(path.read_text().replace("__WORKFLOWS_V1_SHA__", "v1"))
        result = subprocess.run([str(PYTHON), str(ROOT / "scripts/check-workflow-pins.py"), "--root", str(self.root)], text=True, capture_output=True, check=False)
        self.assertNotEqual(result.returncode, 0)

    def test_real_environment_profile_is_rejected_before_kind(self) -> None:
        result = subprocess.run(["bash", str(ROOT / "scripts/run-runtime-smoke.sh"), "--root", str(self.root), "--mode", "local", "--profile", "prod"], text=True, capture_output=True, check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("profile=ci", result.stdout + result.stderr)

    def test_missing_browser_slot_coverage_is_rejected(self) -> None:
        report = self.root / "report.json"
        report.write_text(json.dumps({"suites": []}))
        result = subprocess.run([str(PYTHON), str(ROOT / "scripts/check-browser-report.py"), "--extension", str(self.root / "extension.yaml"), "--report", str(report)], text=True, capture_output=True, check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("cluster-tab:health", result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
