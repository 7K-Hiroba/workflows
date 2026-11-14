from __future__ import annotations

import json
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml

from tests.unit.test_validate_repository import make_valid_repo

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "render-observability.py"
PYTHON = ROOT / ".venv" / "bin" / "python"
if not PYTHON.exists():
    PYTHON = Path("python3")


class RenderObservabilityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        make_valid_repo(self.root)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def run_renderer(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run([str(PYTHON), str(SCRIPT), "--root", str(self.root), *args], text=True, capture_output=True, check=False)

    def test_generates_chart_and_pack_from_canonical_assets(self) -> None:
        result = self.run_renderer()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        dashboard_output = self.root / "charts/workflows-scaffold/templates/observability/dashboards.yaml"
        rules_output = self.root / "charts/workflows-scaffold/templates/observability/rules.yaml"
        pack_output = self.root / "packages/observability-pack/rgd.yaml"
        metadata_output = self.root / "charts/workflows-scaffold/inari/observability.yaml"
        for path in (dashboard_output, rules_output, pack_output, metadata_output):
            self.assertTrue(path.is_file(), path)
            self.assertIn("GENERATED", path.read_text())
        self.assertIn("workflows-scaffold-overview", dashboard_output.read_text())
        self.assertIn("DS_PROMETHEUS", dashboard_output.read_text())
        self.assertNotIn("ServiceMonitor", dashboard_output.read_text() + rules_output.read_text())
        pack = yaml.safe_load(pack_output.read_text())
        self.assertEqual(pack["kind"], "ResourceGraphDefinition")
        self.assertIn("render", pack["spec"]["schema"]["spec"])
        resource_kinds = {resource["template"]["kind"] for resource in pack["spec"]["resources"]}
        self.assertEqual(resource_kinds, {"ConfigMap", "PrometheusRule"})
        for resource in pack["spec"]["resources"]:
            self.assertRegex(resource["id"], re.compile(r"^[a-z][a-zA-Z0-9]*$"))
        dashboard = next(resource for resource in pack["spec"]["resources"] if resource["id"] == "dashboardWorkflowsScaffoldOverview")
        payload = dashboard["template"]["data"]["workflows-scaffold-overview.json"]
        self.assertIn('${"${DS_PROMETHEUS}"}', payload)
        canonical = json.loads((self.root / "observability/dashboards/overview.json").read_text())
        restored = payload.replace('${"${DS_PROMETHEUS}"}', "${DS_PROMETHEUS}")
        self.assertEqual(restored, json.dumps(canonical, indent=2, sort_keys=True) + "\n")
        metadata = yaml.safe_load(metadata_output.read_text())
        self.assertEqual(metadata["app"], "workflows-scaffold")

    def test_check_detects_drift_without_writing(self) -> None:
        self.assertEqual(self.run_renderer().returncode, 0)
        self.assertEqual(self.run_renderer("--check").returncode, 0)
        output = self.root / "packages/observability-pack/rgd.yaml"
        output.write_text("# stale user edit\n")
        result = self.run_renderer("--check")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("out of date", result.stdout + result.stderr)
        self.assertEqual(output.read_text(), "# stale user edit\n")

    def test_missing_canonical_asset_fails(self) -> None:
        (self.root / "observability/dashboards/overview.json").unlink()
        result = self.run_renderer()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("dashboard", (result.stdout + result.stderr).lower())


if __name__ == "__main__":
    unittest.main()
