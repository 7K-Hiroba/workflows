from __future__ import annotations

import subprocess
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / ".github" / "workflows"
PUBLIC = [
    "validate-packages.yml",
    "test-packages.yml",
    "test-runtime-smoke.yml",
    "release-smoke-suite.yml",
    "ci-go-extension.yml",
    "ci-ui-extension.yml",
    "ci-chart.yml",
    "test-observability.yml",
    "compat-check.yml",
    "release-please.yml",
    "release.yml",
    "release-oci.yml",
    "release-chart.yml",
    "release-extension.yml",
    "edge.yml",
]
INTERNAL = ["library-ci.yml", "scaffold-ci.yml", "nightly.yml", "publish-rehearsal.yml", "library-release.yml"]


class WorkflowContractTests(unittest.TestCase):
    def test_all_required_workflows_exist_and_parse(self) -> None:
        for name in PUBLIC + INTERNAL:
            with self.subTest(name=name):
                path = WORKFLOWS / name
                self.assertTrue(path.is_file(), path)
                data = yaml.safe_load(path.read_text())
                self.assertIsInstance(data.get("jobs"), dict)
                self.assertTrue(data["jobs"])

    def test_public_workflows_are_reusable_with_outputs_and_stable_result(self) -> None:
        for name in PUBLIC:
            with self.subTest(name=name):
                data = yaml.safe_load((WORKFLOWS / name).read_text())
                self.assertIn("workflow_call", data.get("on", data.get(True, {})))
                outputs = data.get("on", data.get(True, {}))["workflow_call"].get("outputs")
                self.assertIn("status", outputs)
                self.assertIn("result", data["jobs"])

    def test_library_scripts_use_resolved_same_commit_checkout(self) -> None:
        for path in WORKFLOWS.glob("*.yml"):
            text = path.read_text()
            if "scripts/" not in text:
                continue
            with self.subTest(name=path.name):
                self.assertIn("job.workflow_repository", text)
                self.assertIn("job.workflow_sha", text)
                self.assertIn("path: .hiroba/workflows", text)
                self.assertIn("path: consumer", text)

    def test_ci_lanes_have_no_publish_permissions(self) -> None:
        for name in ("validate-packages.yml", "test-packages.yml", "test-runtime-smoke.yml", "ci-go-extension.yml", "ci-ui-extension.yml", "ci-chart.yml", "test-observability.yml", "compat-check.yml"):
            with self.subTest(name=name):
                text = (WORKFLOWS / name).read_text()
                self.assertNotIn("id-token: write", text)
                self.assertNotIn("packages: write", text)
                self.assertNotIn("attestations: write", text)
                self.assertNotIn("pull_request_target:", text)
                self.assertNotIn("secrets: inherit", text)

    def test_forbidden_dependencies_and_distribution_are_absent(self) -> None:
        for path in WORKFLOWS.glob("*.yml"):
            text = path.read_text()
            with self.subTest(name=path.name):
                self.assertNotIn("inari-operator", text)
                self.assertNotIn("gh release upload", text)
                self.assertNotIn("releases/download", text)
                self.assertNotIn("helm repo add", text)
                self.assertNotIn("index.yaml", text)

    def test_browser_compat_uses_playwright_supported_runner(self) -> None:
        data = yaml.safe_load((WORKFLOWS / "compat-check.yml").read_text())
        self.assertEqual(data["jobs"]["test"]["runs-on"], "ubuntu-24.04")

    def test_chart_install_and_package_diagnostics_use_valid_paths_and_flags(self) -> None:
        chart = (WORKFLOWS / "ci-chart.yml").read_text()
        self.assertIn('--helm-extra-set-args "--set=image.repository=workflows-scaffold', chart)
        self.assertNotIn('--helm-extra-set-args "image.repository=', chart)

        packages = (WORKFLOWS / "test-packages.yml").read_text()
        self.assertIn('path: "consumer/${{ inputs.root }}/diagnostics"', packages)
        self.assertNotIn("path: consumer/diagnostics", packages)

    def test_repository_workflows_pass_pin_policy(self) -> None:
        result = subprocess.run(["python3", str(ROOT / "scripts/check-workflow-pins.py"), "--root", str(ROOT)], text=True, capture_output=True, check=False)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
