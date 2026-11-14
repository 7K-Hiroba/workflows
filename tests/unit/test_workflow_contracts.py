from __future__ import annotations

import fnmatch
import os
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

    def test_reusable_test_lanes_check_out_the_requested_exact_source(self) -> None:
        names = ("validate-packages.yml", "test-packages.yml", "ci-go-extension.yml", "ci-ui-extension.yml", "ci-chart.yml", "test-observability.yml", "compat-check.yml", "test-runtime-smoke.yml")
        for name in names:
            with self.subTest(name=name):
                data = yaml.safe_load((WORKFLOWS / name).read_text())
                inputs = data.get("on", data.get(True, {}))["workflow_call"]["inputs"]
                self.assertIn("source-sha", inputs)
                checkouts = []
                for job in data["jobs"].values():
                    for step in job.get("steps", []):
                        if str(step.get("uses", "")).startswith("actions/checkout@") and step.get("with", {}).get("path") == "consumer":
                            checkouts.append(step)
                self.assertTrue(checkouts)
                for checkout in checkouts:
                    self.assertEqual(checkout["with"].get("ref"), "${{ inputs.source-sha }}")
        release = yaml.safe_load((WORKFLOWS / "release.yml").read_text())
        for name in ("validate", "packages", "go", "ui", "chart", "observability", "compat", "runtime"):
            self.assertEqual(release["jobs"][name]["with"]["source-sha"], "${{ needs.plan.outputs.source-sha }}")
        for name in ("release-chart.yml", "release-smoke-suite.yml"):
            data = yaml.safe_load((WORKFLOWS / name).read_text())
            self.assertEqual(data["jobs"]["test"]["with"]["source-sha"], "${{ inputs.source-sha }}")

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

    def test_chart_install_uses_validated_consumer_declarations(self) -> None:
        chart = (WORKFLOWS / "ci-chart.yml").read_text()
        self.assertIn("scripts/chart-test-config.py", chart)
        self.assertNotIn("workflows-scaffold", chart)
        self.assertNotIn("prometheusrule-crd.yaml", chart)
        self.assertNotIn("--helm-extra-set-args", chart)
        self.assertIn('args+=(--helm-extra-args "--values consumer/', chart)

        packages = (WORKFLOWS / "test-packages.yml").read_text()
        self.assertIn('path: "consumer/${{ inputs.root }}/diagnostics"', packages)
        self.assertNotIn("path: consumer/diagnostics", packages)

    def test_stable_release_and_chart_repair_callers_forward_exact_inputs(self) -> None:
        release = (ROOT / "scaffold/.github/workflows/release.yml.template").read_text()
        self.assertIn('app-id: "${{ vars.HIROBA_RELEASE_APP_ID }}"', release)
        self.assertIn('release-private-key: "${{ secrets.HIROBA_RELEASE_PRIVATE_KEY }}"', release)
        self.assertNotIn("secrets: inherit", release)
        repair_text = (ROOT / "scaffold/.github/workflows/chart-repair.yml.template").read_text()
        repair = yaml.safe_load(repair_text)
        self.assertIn("resolve", repair["jobs"])
        self.assertEqual(repair["jobs"]["repair"]["needs"], "resolve")
        self.assertEqual(repair["jobs"]["repair"]["with"]["source-sha"], "${{ needs.resolve.outputs.source-sha }}")
        self.assertIn('refs/tags/$TAG^{}', repair_text)

    def test_edge_threads_versions_and_channels_through_every_publisher(self) -> None:
        release = yaml.safe_load((WORKFLOWS / "release.yml").read_text())
        extension = release["jobs"]["publish-extension"]["with"]
        self.assertEqual(extension["edge"], "${{ inputs.edge }}")
        self.assertEqual(extension["backend-version"], "${{ needs.plan.outputs.extension-version }}")
        self.assertEqual(extension["ui-version"], "${{ needs.plan.outputs.ui-version }}")
        smoke = release["jobs"]["publish-smoke"]["with"]
        self.assertEqual(smoke["edge"], "${{ inputs.edge }}")
        self.assertEqual(smoke["target-version"], "${{ needs.plan.outputs.smoke-version }}")
        self.assertEqual(release["jobs"]["publish-charts"]["with"]["edge"], "${{ inputs.edge }}")
        for name in ("release-extension.yml", "release-smoke-suite.yml", "release-chart.yml"):
            data = yaml.safe_load((WORKFLOWS / name).read_text())
            self.assertIn("edge", data.get("on", data.get(True, {}))["workflow_call"]["inputs"])
            text = (WORKFLOWS / name).read_text()
            self.assertIn('oras tag', text)
        extension_text = (WORKFLOWS / "release-extension.yml").read_text()
        self.assertIn('version="${{ inputs.backend-version }}"', extension_text)
        self.assertIn('version="${{ inputs.ui-version }}"', extension_text)
        smoke_text = (WORKFLOWS / "release-smoke-suite.yml").read_text()
        self.assertIn('version="${{ inputs.target-version }}"', smoke_text)

    def test_extension_ui_evidence_uses_the_finalizer_artifact_contract(self) -> None:
        extension = yaml.safe_load((WORKFLOWS / "release-extension.yml").read_text())
        uploads = [step for step in extension["jobs"]["ui"]["steps"] if str(step.get("uses", "")).startswith("actions/upload-artifact@")]
        names = [step["with"]["name"] for step in uploads]
        self.assertIn("artifact-extension-ui", names)
        release = yaml.safe_load((WORKFLOWS / "release.yml").read_text())
        downloads = [step for step in release["jobs"]["finalize"]["steps"] if str(step.get("uses", "")).startswith("actions/download-artifact@")]
        patterns = [step["with"]["pattern"] for step in downloads]
        self.assertTrue(any(fnmatch.fnmatch("artifact-extension-ui", pattern) for pattern in patterns))

    def test_render_job_installs_actionlint_for_rendered_callers(self) -> None:
        data = yaml.safe_load((WORKFLOWS / "library-ci.yml").read_text())
        steps = data["jobs"]["render"]["steps"]
        self.assertTrue(any(str(step.get("uses", "")).startswith("actions/setup-go@") for step in steps))
        self.assertTrue(any("go install github.com/rhysd/actionlint/cmd/actionlint@v1.7.12" in str(step.get("run", "")) for step in steps))
        self.assertTrue(any("lint-rendered-workflows.sh" in str(step.get("run", "")) for step in steps))

    def test_shell_entrypoints_used_directly_by_workflows_are_executable(self) -> None:
        for name in ("lint-rendered-workflows.sh", "release-backend.sh"):
            with self.subTest(name=name):
                self.assertTrue(os.access(ROOT / "scripts" / name, os.X_OK), name)

    def test_repository_workflows_pass_pin_policy(self) -> None:
        result = subprocess.run(["python3", str(ROOT / "scripts/check-workflow-pins.py"), "--root", str(ROOT)], text=True, capture_output=True, check=False)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
