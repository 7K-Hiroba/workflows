from __future__ import annotations

import fnmatch
import os
import re
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

    def test_publisher_verification_uses_exact_workflow_ref_san(self) -> None:
        expected_jobs = {
            "release-oci.yml": ("publish",),
            "release-extension.yml": ("backend", "ui"),
            "release-chart.yml": ("publish",),
            "release-smoke-suite.yml": ("publish",),
        }
        for workflow_name, job_names in expected_jobs.items():
            workflow = yaml.safe_load((WORKFLOWS / workflow_name).read_text())
            for job_name in job_names:
                with self.subTest(workflow=workflow_name, job=job_name):
                    steps = [step for step in workflow["jobs"][job_name]["steps"] if "EXPECTED_PUBLISHER" in step.get("env", {})]
                    self.assertEqual(len(steps), 1)
                    env = steps[0]["env"]
                    escaped_name = workflow_name.replace(".", "\\.")
                    expected = f"^https://github\\.com/7K-Hiroba/workflows/\\.github/workflows/{escaped_name}@${{{{ github.ref }}}}$"
                    self.assertEqual(env["EXPECTED_PUBLISHER"], expected)
                    self.assertEqual(env["WORKFLOW_SHA"], "${{ job.workflow_sha }}")
                    self.assertTrue(env["SOURCE_SHA"])
                    pattern = env["EXPECTED_PUBLISHER"].replace("${{ github.ref }}", "refs/heads/main")
                    identity = f"https://github.com/7K-Hiroba/workflows/.github/workflows/{workflow_name}@refs/heads/main"
                    self.assertIsNotNone(re.fullmatch(pattern, identity))
                    self.assertNotIn(".*", pattern)
                    for different_ref in ("refs/heads/main-next", "refs/heads/feature", "refs/tags/main", "a" * 40):
                        self.assertIsNone(re.fullmatch(pattern, identity.replace("refs/heads/main", different_ref)))

    def test_every_release_verification_step_receives_github_token(self) -> None:
        expected = {
            ("release-oci.yml", "publish"),
            ("release-extension.yml", "backend"),
            ("release-extension.yml", "ui"),
            ("release-chart.yml", "publish"),
            ("release-smoke-suite.yml", "publish"),
        }
        verify_steps = {}
        for path in WORKFLOWS.glob("release-*.yml"):
            workflow = yaml.safe_load(path.read_text())
            for job_name, job in workflow["jobs"].items():
                for step in job.get("steps", []):
                    if step.get("run") == ".hiroba/workflows/scripts/verify-release.sh":
                        verify_steps[(path.name, job_name)] = step
        self.assertEqual(set(verify_steps), expected)
        for identity, step in verify_steps.items():
            with self.subTest(workflow=identity[0], job=identity[1]):
                env = step["env"]
                self.assertEqual(env.get("GH_TOKEN"), "${{ github.token }}")
                for field in ("SOURCE_SHA", "WORKFLOW_SHA", "ARTIFACT_DIGEST", "REQUIRED_LANES", "VERIFICATION_RECEIPT"):
                    self.assertTrue(env.get(field), field)
                self.assertIn("${{ github.ref }}", env["EXPECTED_PUBLISHER"])

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

    def test_extension_ui_setup_node_uses_default_no_cache_behavior(self) -> None:
        workflow = yaml.safe_load((WORKFLOWS / "release-extension.yml").read_text())
        steps = [step for step in workflow["jobs"]["ui"]["steps"] if str(step.get("uses", "")).startswith("actions/setup-node@")]
        self.assertEqual(len(steps), 1)
        self.assertEqual(steps[0]["with"]["node-version"], 24)
        self.assertNotIn("cache", steps[0]["with"])

    def test_chart_install_uses_validated_consumer_declarations(self) -> None:
        chart = (WORKFLOWS / "ci-chart.yml").read_text()
        self.assertIn("scripts/chart-test-config.py", chart)
        self.assertNotIn("workflows-scaffold", chart)
        self.assertNotIn("prometheusrule-crd.yaml", chart)
        self.assertNotIn("--helm-extra-set-args", chart)
        self.assertNotIn('args+=(--helm-extra-args "--values', chart)

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
        for job_name in ("publish-packages", "publish-templates"):
            self.assertEqual(release["jobs"][job_name]["with"]["version"], "${{ matrix.component.version }}")
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
            self.assertNotIn('oras tag', text)
        extension_text = (WORKFLOWS / "release-extension.yml").read_text()
        self.assertIn('version="${{ inputs.backend-version }}"', extension_text)
        self.assertIn('version="${{ inputs.ui-version }}"', extension_text)
        smoke_text = (WORKFLOWS / "release-smoke-suite.yml").read_text()
        self.assertIn('version="${{ inputs.target-version }}"', smoke_text)

    def test_non_default_component_paths_flow_through_execution_and_release(self) -> None:
        for name, output in (("ci-go-extension.yml", "extension-path"), ("ci-ui-extension.yml", "ui-path"), ("compat-check.yml", "extension-path")):
            workflow = yaml.safe_load((WORKFLOWS / name).read_text())
            self.assertIn(output, workflow["jobs"]["plan"]["outputs"])
            self.assertIn("plan", workflow["jobs"]["test"]["needs"])
        compat = yaml.safe_load((WORKFLOWS / "compat-check.yml").read_text())
        self.assertIn("ui-path", compat["jobs"]["plan"]["outputs"])
        self.assertIn('"$ROOT/$EXTENSION_PATH"', (ROOT / "scripts/run-compat-backend.sh").read_text())
        self.assertIn('UI_DIR="$ROOT/$UI_PATH"', (ROOT / "scripts/run-compat-browser.sh").read_text())
        extension = yaml.safe_load((WORKFLOWS / "release-extension.yml").read_text())
        inputs = extension.get("on", extension.get(True, {}))["workflow_call"]["inputs"]
        self.assertIn("backend-path", inputs)
        self.assertIn("ui-path", inputs)
        release = yaml.safe_load((WORKFLOWS / "release.yml").read_text())
        self.assertEqual(release["jobs"]["publish-extension"]["with"]["backend-path"], "${{ needs.plan.outputs.extension-path }}")
        self.assertEqual(release["jobs"]["publish-extension"]["with"]["ui-path"], "${{ needs.plan.outputs.ui-path }}")
        packages = (WORKFLOWS / "test-packages.yml").read_text()
        for name in ("kro", "policy", "app"):
            self.assertIn(name, packages)
            self.assertIn('--package-path "${{ matrix.package.path }}"', packages)
        runtime = (ROOT / "scripts/run-runtime-smoke.sh").read_text()
        self.assertIn('select(.kind == "smoke") | .path', runtime)
        smoke = (WORKFLOWS / "release-smoke-suite.yml").read_text()
        self.assertIn("steps.config.outputs.suite-path", smoke)

    def test_channel_coordinator_gates_all_artifacts_and_indexes(self) -> None:
        publisher = (WORKFLOWS / "release-oci.yml").read_text()
        self.assertNotIn("oras tag", publisher)
        release = yaml.safe_load((WORKFLOWS / "release.yml").read_text())
        channels = release["jobs"]["channels"]
        for needed in ("publish-packages", "publish-templates", "publish-charts", "publish-extension", "publish-smoke", "indexes"):
            self.assertIn(needed, channels["needs"])
        self.assertIn("needs.indexes.outputs.status == 'success'", channels["if"])
        self.assertIn("channels", release["jobs"]["finalize"]["needs"])
        self.assertIn("needs.channels.outputs.status == 'success'", release["jobs"]["finalize"]["if"])
        self.assertIn("channels", release["jobs"]["edge-release"]["needs"])
        self.assertIn("needs.channels.outputs.status == 'success'", release["jobs"]["edge-release"]["if"])

    def test_publish_rehearsal_permission_chain_is_complete_and_scoped(self) -> None:
        approved = {"contents": "write", "actions": "read", "packages": "write", "id-token": "write", "attestations": "write"}
        access_level = {"none": 0, "read": 1, "write": 2}
        workflows = {path.name: yaml.safe_load(path.read_text()) for path in WORKFLOWS.glob("*.yml")}
        required_cache = {}
        failures = []

        def merge_required(required, candidate):
            for scope, access in candidate.items():
                if access_level[access] > access_level[required.get(scope, "none")]:
                    required[scope] = access

        def required_permissions(workflow_name):
            if workflow_name in required_cache:
                return required_cache[workflow_name]
            workflow = workflows[workflow_name]
            required = dict(workflow.get("permissions", {}))
            for job in workflow["jobs"].values():
                merge_required(required, job.get("permissions", {}))
                uses = str(job.get("uses", ""))
                if uses.startswith("$/"):
                    merge_required(required, required_permissions(uses.rsplit("/", 1)[-1]))
            required_cache[workflow_name] = required
            return required

        def check_supported(owner, permissions):
            for scope, access in permissions.items():
                if scope not in approved or access_level[access] > access_level[approved[scope]]:
                    failures.append(f"{owner} grants unsupported {scope}: {access}")

        checked_edges = set()
        visited = set()

        def audit(workflow_name):
            if workflow_name in visited:
                return
            visited.add(workflow_name)
            workflow = workflows[workflow_name]
            check_supported(workflow_name, workflow.get("permissions", {}))
            for job_name, job in workflow["jobs"].items():
                owner = f"{workflow_name}:{job_name}"
                allowed = job.get("permissions", workflow.get("permissions", {}))
                check_supported(owner, allowed)
                uses = str(job.get("uses", ""))
                if not uses.startswith("$/"):
                    continue
                called = uses.rsplit("/", 1)[-1]
                checked_edges.add((workflow_name, job_name, called))
                for scope, access in required_permissions(called).items():
                    granted = allowed.get(scope, "none")
                    if access_level[granted] < access_level[access]:
                        failures.append(f"{owner} grants {scope}: {granted}; {called} requires {access}")
                audit(called)

        audit("publish-rehearsal.yml")
        expected_edges = {
            ("publish-rehearsal.yml", "full", "release.yml"),
            ("publish-rehearsal.yml", "reuse-chart", "release-chart.yml"),
            ("release.yml", "validate", "validate-packages.yml"),
            ("release.yml", "packages", "test-packages.yml"),
            ("release.yml", "go", "ci-go-extension.yml"),
            ("release.yml", "ui", "ci-ui-extension.yml"),
            ("release.yml", "chart", "ci-chart.yml"),
            ("release.yml", "observability", "test-observability.yml"),
            ("release.yml", "compat", "compat-check.yml"),
            ("release.yml", "runtime", "test-runtime-smoke.yml"),
            ("release.yml", "publish-packages", "release-oci.yml"),
            ("release.yml", "publish-templates", "release-oci.yml"),
            ("release.yml", "publish-charts", "release-chart.yml"),
            ("release.yml", "publish-extension", "release-extension.yml"),
            ("release.yml", "publish-smoke", "release-smoke-suite.yml"),
            ("release.yml", "indexes", "release-oci.yml"),
            ("release-chart.yml", "test", "ci-chart.yml"),
            ("release-smoke-suite.yml", "test", "test-runtime-smoke.yml"),
        }
        self.assertEqual(checked_edges, expected_edges)
        self.assertEqual(failures, [])
        self.assertEqual(workflows["release.yml"]["permissions"], approved)
        self.assertEqual(workflows["publish-rehearsal.yml"]["jobs"]["reuse-chart"]["permissions"]["contents"], "read")

    def test_release_mutations_are_serialized_per_consumer_without_cancellation(self) -> None:
        paths = [
            ROOT / "scaffold/.github/workflows/release.yml.template",
            ROOT / "scaffold/.github/workflows/edge.yml.template",
            ROOT / "scaffold/.github/workflows/chart-repair.yml.template",
            WORKFLOWS / "library-release.yml",
            WORKFLOWS / "publish-rehearsal.yml",
        ]
        for path in paths:
            with self.subTest(path=path.name):
                data = yaml.safe_load(path.read_text())
                concurrency = data.get("concurrency")
                self.assertIsInstance(concurrency, dict)
                self.assertIn("github.repository", concurrency["group"])
                self.assertIs(concurrency["cancel-in-progress"], False)
        consumer_groups = [yaml.safe_load(path.read_text())["concurrency"]["group"] for path in paths[:3]]
        self.assertEqual(len(set(consumer_groups)), 1)

    def test_library_release_please_uses_static_manifest_mode(self) -> None:
        library = yaml.safe_load((WORKFLOWS / "library-release-please.yml").read_text())
        self.assertIs(library["jobs"]["propose"]["with"]["library-mode"], True)
        reusable = yaml.safe_load((WORKFLOWS / "release-please.yml").read_text())
        inputs = reusable.get("on", reusable.get(True, {}))["workflow_call"]["inputs"]
        self.assertEqual(inputs["library-mode"], {"type": "boolean", "default": False})
        sync = next(step for step in reusable["jobs"]["propose"]["steps"] if step.get("id") == "sync")
        self.assertIn("inputs.library-mode == false", sync["if"])
        self.assertFalse((ROOT / ".hiroba.yaml").exists())

    def test_library_release_gitsign_uses_exact_ref_san(self) -> None:
        text = (WORKFLOWS / "library-release.yml").read_text()
        workflow = yaml.safe_load(text)
        release = workflow["jobs"]["release"]
        self.assertEqual(release["environment"], "release")
        self.assertEqual(release["permissions"], {"contents": "write", "id-token": "write", "actions": "read"})
        app = next(step for step in release["steps"] if str(step.get("uses", "")).startswith("actions/create-github-app-token@"))
        self.assertEqual(app["with"]["app-id"], "${{ vars.HIROBA_RELEASE_APP_ID }}")
        self.assertEqual(app["with"]["private-key"], "${{ secrets.HIROBA_RELEASE_PRIVATE_KEY }}")
        checkout = next(step for step in release["steps"] if step.get("with", {}).get("path") == "consumer")
        self.assertEqual(checkout["with"]["token"], "${{ steps.app.outputs.token }}")
        checks = next(step for step in release["steps"] if step.get("name") == "Verify approved main and required checks")
        self.assertEqual(checks["env"]["GH_TOKEN"], "${{ steps.app.outputs.token }}")
        for fragment in ("check-required-checks.py", "library-ci-result", "scaffold-ci-result", ".release-please-manifest.json", "CHANGELOG.md", "source-sha"):
            self.assertIn(fragment, checks["run"])
        signed = next(step for step in release["steps"] if step.get("name") == "Create and verify signed version tag")
        self.assertEqual(signed["env"]["GH_TOKEN"], "${{ steps.app.outputs.token }}")
        self.assertIn("gh release create", signed["run"])
        major = next(step for step in release["steps"] if step.get("name") == "Optionally move signed documentation-only major alias")
        self.assertEqual(major["if"], "inputs.update_major")
        self.assertIn("go install github.com/sigstore/gitsign@v0.18.0", text)

        patterns = re.findall(r'--certificate-identity-regexp "([^"]+)"', text)
        self.assertEqual(len(patterns), 2)
        identity = "https://github.com/7K-Hiroba/workflows/.github/workflows/library-release.yml@refs/heads/main"
        for pattern in patterns:
            self.assertIn("${{ github.ref }}", pattern)
            self.assertNotIn("job.workflow_sha", pattern)
            actual = pattern.replace("\\\\", "\\").replace("${{ github.ref }}", "refs/heads/main")
            self.assertIsNotNone(re.fullmatch(actual, identity))
            self.assertNotIn(".*", actual)
            for different_ref in ("88f60a279b6676689e75388a080130d1902674f9", "refs/heads/main-next", "refs/heads/feature", "refs/tags/main"):
                self.assertIsNone(re.fullmatch(actual, identity.replace("refs/heads/main", different_ref)))

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
