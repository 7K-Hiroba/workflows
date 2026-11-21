from __future__ import annotations

import json
import re
import shutil
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

    def test_v2_rules_respect_evaluation_and_boolean_gates(self) -> None:
        manifest = self.root / "observability/observability.yaml"
        data = yaml.safe_load(manifest.read_text())
        data["rules"].append({"file": "rules/local.yaml", "evaluation": "local"})
        manifest.write_text(yaml.safe_dump(data, sort_keys=False))
        (self.root / "observability/rules/local.yaml").write_text("groups: []\n")

        result = self.run_renderer()

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        pack = yaml.safe_load((self.root / "packages/observability-pack/rgd.yaml").read_text())
        self.assertEqual(pack["metadata"]["annotations"]["inari.dev/observability-render-contract"], "inari.observability-pack/v2")
        resources = {resource["id"]: resource for resource in pack["spec"]["resources"]}
        self.assertEqual(
            resources["rulesCentral"]["includeWhen"][0],
            '${(schema.spec.render == "all" || schema.spec.render == "rules-central") && schema.spec.rulesCentral}',
        )
        self.assertEqual(
            resources["rulesLocal"]["includeWhen"][0],
            '${(schema.spec.render == "all" || schema.spec.render == "rules-local") && schema.spec.rulesLocal}',
        )
        for evaluation, gate in (("Central", "rulesCentral"), ("Local", "rulesLocal")):
            resource_id = "rulesConfig" + evaluation
            self.assertIn(resource_id, resources)
            config_map = resources[resource_id]
            self.assertEqual("ConfigMap", config_map["template"]["kind"])
            self.assertEqual(config_map["includeWhen"], resources["rules" + evaluation]["includeWhen"])
            self.assertEqual("monitoring.coreos.com/v1", resources["rules" + evaluation]["template"]["apiVersion"])
            self.assertEqual("${schema.spec.app}-" + evaluation.lower() + "-rules", config_map["template"]["metadata"]["name"])
            self.assertEqual(evaluation.lower(), config_map["template"]["metadata"]["labels"]["inari.dev/rule-evaluation"])
            self.assertIn("groups:", config_map["template"]["data"][evaluation.lower() + ".yaml"])

    def test_app_package_contains_full_signed_observability_manifest(self) -> None:
        package = self.root / "packages/app/package.yaml"
        package.write_text(package.read_text() + "observability:\n  package: observability-pack\n  versionRange: '>=0.1.0 <2.0.0'\n")

        result = self.run_renderer()

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        metadata = self.root / "packages/app/observability.yaml"
        self.assertTrue(metadata.is_file())
        canonical = yaml.safe_load((self.root / "observability/observability.yaml").read_text())
        generated = metadata.read_text()
        self.assertTrue(generated.startswith("# GENERATED by scripts/render-observability.py; DO NOT EDIT.\n"))
        self.assertEqual(yaml.safe_load(generated), canonical)

    def test_check_detects_drift_without_writing(self) -> None:
        self.assertEqual(self.run_renderer().returncode, 0)
        self.assertEqual(self.run_renderer("--check").returncode, 0)
        output = self.root / "packages/observability-pack/rgd.yaml"
        output.write_text("# stale user edit\n")
        result = self.run_renderer("--check")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("out of date", result.stdout + result.stderr)
        self.assertEqual(output.read_text(), "# stale user edit\n")

    def test_chartless_generates_pack_without_chart_outputs(self) -> None:
        config = self.root / ".hiroba.yaml"
        config.write_text(config.read_text().replace("  chart: charts/workflows-scaffold\n", ""))
        shutil.rmtree(self.root / "charts")

        result = self.run_renderer()

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue((self.root / "packages/observability-pack/rgd.yaml").is_file())
        self.assertFalse((self.root / "charts").exists())

    def test_chartless_check_does_not_create_missing_output_directories(self) -> None:
        config = self.root / ".hiroba.yaml"
        config.write_text(config.read_text().replace("  chart: charts/workflows-scaffold\n", ""))
        shutil.rmtree(self.root / "charts")
        shutil.rmtree(self.root / "packages/observability-pack")

        result = self.run_renderer("--check")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("out of date", result.stdout + result.stderr)
        self.assertFalse((self.root / "charts").exists())
        self.assertFalse((self.root / "packages/observability-pack").exists())

    def test_chartless_regeneration_removes_only_stale_generated_chart_outputs(self) -> None:
        self.assertEqual(self.run_renderer().returncode, 0)
        custom = self.root / "charts/workflows-scaffold/templates/observability/custom.yaml"
        custom.write_text("user-owned\n")
        unrelated = self.root / "charts/workflows-scaffold/templates/user.yaml"
        unrelated.write_text("user-owned\n")
        config = self.root / ".hiroba.yaml"
        config.write_text(config.read_text().replace("  chart: charts/workflows-scaffold\n", ""))

        result = self.run_renderer()

        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        for rel in ("templates/observability/dashboards.yaml", "templates/observability/rules.yaml", "inari/observability.yaml"):
            self.assertFalse((self.root / "charts/workflows-scaffold" / rel).exists(), rel)
        self.assertEqual(custom.read_text(), "user-owned\n")
        self.assertEqual(unrelated.read_text(), "user-owned\n")
        self.assertTrue((self.root / "packages/observability-pack/rgd.yaml").is_file())

    def test_chartless_check_rejects_stale_outputs_without_deleting(self) -> None:
        self.assertEqual(self.run_renderer().returncode, 0)
        config = self.root / ".hiroba.yaml"
        config.write_text(config.read_text().replace("  chart: charts/workflows-scaffold\n", ""))
        stale = self.root / "charts/workflows-scaffold/inari/observability.yaml"

        result = self.run_renderer("--check")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("stale", result.stdout + result.stderr)
        self.assertTrue(stale.exists())

    def test_missing_canonical_asset_fails(self) -> None:
        (self.root / "observability/dashboards/overview.json").unlink()
        result = self.run_renderer()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("dashboard", (result.stdout + result.stderr).lower())


if __name__ == "__main__":
    unittest.main()
