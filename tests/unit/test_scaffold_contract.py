from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
SCAFFOLD = ROOT / "scaffold"
PYTHON = ROOT / ".venv" / "bin" / "python"
if not PYTHON.exists():
    PYTHON = Path("python3")


class ScaffoldContractTests(unittest.TestCase):
    def run_script(self, name: str, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run([str(PYTHON), str(ROOT / "scripts" / name), "--root", str(SCAFFOLD), *args], text=True, capture_output=True, check=False)

    def test_scaffold_validates_against_registry(self) -> None:
        result = self.run_script("validate-repository.py", "--registry", str(ROOT / "tests/fixtures/app-registry.yaml"))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_generated_outputs_are_in_sync(self) -> None:
        for script in ("build-indexes.py", "sync-release-please-config.py", "render-observability.py"):
            with self.subTest(script=script):
                result = self.run_script(script, "--check")
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_component_matrix_is_complete(self) -> None:
        result = self.run_script("discover-components.py", "--all")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        plan = json.loads(result.stdout)
        kinds = {component["kind"] for component in plan["components"]}
        self.assertEqual(kinds, {"extension", "ui", "chart", "package", "template", "smoke"})

    def test_scaffold_stack_lifecycle_is_declared_and_hosted(self) -> None:
        result = self.run_script("stack-test-config.py")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        plan = json.loads(result.stdout)
        self.assertEqual(plan["archetype"], "stack")
        self.assertTrue(plan["enabled"])
        self.assertEqual(set(plan["covers"]), {"charts/workflows-scaffold", "packages/observability-pack"})
        self.assertEqual(plan["setupProfiles"], ["kro"])
        self.assertNotIn("argo", plan["setupProfiles"])
        caller = SCAFFOLD / ".github/workflows/stack-test.yml.template"
        self.assertTrue(caller.is_file())
        self.assertIn("test-stack.yml@__WORKFLOWS_V1_SHA__", caller.read_text())
        self.assertIn("merge tree", caller.read_text())
        evidence_doc = (ROOT / "docs/stack-testing.md").read_text()
        self.assertIn("head_sha", evidence_doc)
        self.assertIn("merge tree", evidence_doc)
        workflow = yaml.safe_load((ROOT / ".github/workflows/scaffold-ci.yml").read_text())
        self.assertEqual(workflow["jobs"]["stack"]["uses"], "$/.github/workflows/test-stack.yml")
        self.assertIn("stack", workflow["jobs"]["result"]["needs"])
        self.assertIn("scaffold/tests", (ROOT / "Makefile").read_text())

    def test_full_matrix_fixtures_validate(self) -> None:
        fixtures = {
            "chartless-observability": {"package"},
            "non-plugin-runtime": {"package", "chart", "smoke"},
            "chartless-runtime": {"template", "smoke"},
            "artifact-bound-runtime": {"package", "smoke"},
        }
        for name, kinds in fixtures.items():
            with self.subTest(name=name):
                root = ROOT / "tests/fixtures" / name
                result = self.run_script("validate-repository.py", "--root", str(root))
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                discovered = self.run_script("discover-components.py", "--root", str(root), "--all")
                self.assertEqual(discovered.returncode, 0, discovered.stdout + discovered.stderr)
                self.assertEqual({item["kind"] for item in json.loads(discovered.stdout)["components"]}, kinds)
        chartless = yaml.safe_load((ROOT / "tests/fixtures/chartless-observability/.hiroba.yaml").read_text())
        self.assertNotIn("chart", chartless["observability"])
        self.assertFalse((ROOT / "tests/fixtures/chartless-observability/charts").exists())
        artifact = yaml.safe_load((ROOT / "tests/fixtures/artifact-bound-runtime/tests/smoke/suite.yaml").read_text())
        self.assertEqual(artifact["target"]["component"], "packages/runtime-fixture")
        self.assertEqual(artifact["target"]["adapter"]["artifactPath"], "manifests.yaml")
        self.assertFalse(artifact["target"]["adapter"]["fixtureOnly"])

    def test_non_plugin_chart_has_working_nginx_probes_and_writable_state(self) -> None:
        deployment = (ROOT / "tests/fixtures/non-plugin-runtime/charts/hiroba-nonplugin-smoke/templates/deployment.yaml").read_text()
        self.assertIn("httpGet: {path: /, port: http}", deployment)
        self.assertNotIn("path: /healthz", deployment)
        self.assertIn("readOnlyRootFilesystem: true", deployment)
        self.assertIn("runAsUser: 101", deployment)
        for mount in ("/var/cache/nginx", "/var/run", "/tmp"):
            self.assertIn(mount, deployment)
        self.assertIn("emptyDir", deployment)

    def test_full_matrix_fixture_hosted_lanes_are_wired(self) -> None:
        workflow = yaml.safe_load((ROOT / ".github/workflows/scaffold-ci.yml").read_text())
        roots = {job.get("with", {}).get("root") for job in workflow["jobs"].values()}
        for name in ("chartless-observability", "non-plugin-runtime", "chartless-runtime", "artifact-bound-runtime"):
            self.assertIn(f"tests/fixtures/{name}", roots)

    def test_caller_templates_are_pin_safe(self) -> None:
        result = self.run_script("check-workflow-pins.py")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        rendered = self.run_script("check-workflow-pins.py", "--require-rendered")
        self.assertNotEqual(rendered.returncode, 0)

    def test_image_uses_numeric_nonroot_user(self) -> None:
        dockerfile = (SCAFFOLD / "extension/Dockerfile").read_text()
        self.assertIn("USER 65532:65532", dockerfile)
        self.assertNotIn("USER nonroot:nonroot", dockerfile)

    def test_kro_fixture_uses_the_namespace_asserted_by_its_test(self) -> None:
        package = SCAFFOLD / "packages/observability-pack"
        fixture = yaml.safe_load((package / "tests/fixture.yaml").read_text())
        namespace = fixture["spec"]["namespace"]
        assertions = (package / "tests/run.sh").read_text()
        self.assertEqual(namespace, "default")
        self.assertIn(f"-n {namespace}", assertions)

    def test_compat_matrix_tracks_current_and_previous_stable_ui(self) -> None:
        matrix = json.loads((SCAFFOLD / "ci/compatibility-matrix.json").read_text())
        self.assertEqual([entry["ui"] for entry in matrix["entries"]], ["2.1.1", "2.0.0"])
        self.assertEqual(matrix["entries"][0]["uiHostSha"], "e2562aff1e23fb61cba41d378147a2f508b505d3")

    def test_browser_compat_uses_offline_host_fixture(self) -> None:
        browser = (SCAFFOLD / "ui/tests/browser.spec.ts").read_text()
        self.assertIn("baseURL}/acme/extensions", browser)
        self.assertIn("getByRole('link', { name: 'Clusters'", browser)
        self.assertIn("getByText('ready'", browser)
        self.assertIn("test('slot cluster-tab:health'", browser)
        driver = (ROOT / "scripts/run-compat-browser.sh").read_text()
        self.assertIn("NODE_ENV=development VITE_MOCK_API=true", driver)
        self.assertIn("--oidc-fixture", driver)
        self.assertIn("./node_modules/.bin/playwright test --reporter=json", driver)

    def test_smoke_container_uses_verified_numeric_nonroot_identity(self) -> None:
        workflow = yaml.safe_load((SCAFFOLD / "tests/smoke/workflowtemplate.yaml").read_text())
        container = workflow["spec"]["templates"][0]["container"]
        security = container["securityContext"]
        self.assertTrue(security["runAsNonRoot"])
        self.assertEqual(security["runAsUser"], 100)
        self.assertEqual(security["runAsGroup"], 101)

    def test_ui_uses_only_public_sdk_and_canonical_build(self) -> None:
        package = json.loads((SCAFFOLD / "ui/package.json").read_text())
        self.assertEqual(package["dependencies"]["@7k-inari/ui-plugin-sdk"], "0.1.8")
        extension = yaml.safe_load((SCAFFOLD / "extension.yaml").read_text())
        self.assertEqual(extension["spec"]["contracts"]["ui"]["sdk"], ">=0.1.8 <2.0.0")
        self.assertEqual(package["scripts"]["build"], "inari-ui-ext build --name workflows-scaffold")
        self.assertFalse((SCAFFOLD / "ui/webpack.config.mjs").exists())
        source = "\n".join(path.read_text() for path in (SCAFFOLD / "ui").rglob("*.ts*") if "node_modules" not in path.parts)
        self.assertNotIn("build-sdk", source)
        self.assertNotIn("postinstall", source)


if __name__ == "__main__":
    unittest.main()
