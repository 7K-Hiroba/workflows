from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "validate-repository.py"
PYTHON = ROOT / ".venv" / "bin" / "python"
if not PYTHON.exists():
    PYTHON = Path("python3")


def write(root: Path, relative: str, content: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def make_valid_repo(root: Path) -> None:
    write(
        root,
        ".hiroba.yaml",
        """schema: inari.hiroba.app.v1
app: workflows-scaffold
trustTier: reviewed
components:
  extension: {path: extension, version: 0.1.0}
  ui: {path: ui, version: 0.1.0}
  chartsRoot: charts
  packagesRoot: packages
  templatesRoot: templates
observability:
  path: observability
  chart: charts/workflows-scaffold
  package: packages/observability-pack
  alloyConfig: observability/tests/alloy/config.river
smoke:
  path: tests/smoke
  targetComponent: charts/workflows-scaffold
compatibility:
  matrix: ci/compatibility-matrix.json
""",
    )
    write(root, "extension/go.mod", "module example.com/workflows-scaffold\n\ngo 1.25\n")
    write(
        root,
        "extension.yaml",
        """apiVersion: inari.io/v1alpha1
kind: Extension
metadata: {name: workflows-scaffold}
spec:
  version: 0.1.0
  kinds: [backend, ui]
  backend:
    image: ghcr.io/7k-hiroba/workflows-scaffold/extension
    digestPinning: required
  ui:
    remoteEntryOci: ghcr.io/7k-hiroba/workflows-scaffold/extension-ui
    slots: [{kind: cluster-tab, name: health}]
  contracts:
    backend: [inari.plugin.v1]
    ui: {sdk: '>=0.1.7 <2.0.0', hostApi: inari.ui.v1}
""",
    )
    write(root, "ui/package.json", json.dumps({"name": "workflows-scaffold-ui", "version": "0.1.0"}))
    write(
        root,
        "charts/workflows-scaffold/Chart.yaml",
        "apiVersion: v2\nname: workflows-scaffold\nversion: 0.1.0\n",
    )
    write(root, "charts/workflows-scaffold/values.yaml", "image: {}\n")
    packages = {
        "app": "platform-app",
        "observability-pack": "kro-rgd",
        "admission-example": "policy-pack",
    }
    for name, kind in packages.items():
        write(
            root,
            f"packages/{name}/package.yaml",
            f"version: 0.1.0\nchannel: incubating\ntype: {kind}\ndescription: {name}\ncategory: test\n",
        )
        write(root, f"packages/{name}/README.md", f"# {name}\n")
        write(root, f"packages/{name}/tests/run.sh", "#!/usr/bin/env bash\nexit 0\n")
        if kind == "platform-app":
            write(
                root,
                f"packages/{name}/chart.yaml",
                "repoURL: oci://ghcr.io/7k-hiroba/workflows-scaffold/charts\nchart: workflows-scaffold\nnamespace: default\nchannels: {incubating: 0.1.0}\n",
            )
            write(root, f"packages/{name}/values-defaults.yaml", "replicas: 1\n")
            write(
                root,
                f"packages/{name}/values.schema.json",
                json.dumps({"type": "object", "properties": {"replicas": {"type": "integer", "minimum": 1}}}),
            )
        elif kind == "kro-rgd":
            write(root, f"packages/{name}/ui-hints.yaml", "{}\n")
            write(
                root,
                f"packages/{name}/rgd.yaml",
                """apiVersion: kro.run/v1alpha1
kind: ResourceGraphDefinition
metadata: {name: observability-pack}
spec:
  schema:
    apiVersion: v1alpha1
    kind: Observability
    spec: {app: string}
  resources:
    - id: dashboard
      template:
        apiVersion: v1
        kind: ConfigMap
        metadata:
          name: ${schema.spec.app}
""",
            )
        else:
            write(root, f"packages/{name}/policies.yaml", "apiVersion: admissionregistration.k8s.io/v1\nkind: ValidatingAdmissionPolicy\n")
    write(
        root,
        "templates/service/template.yaml",
        "name: service\nversion: 0.1.0\nchannel: incubating\ndescription: Service template\nkind: component\n",
    )
    write(root, "templates/service/schema.json", json.dumps({"type": "object"}))
    write(root, "templates/service/uiSchema.json", "{}\n")
    write(root, "templates/service/skeleton/README.md", "# service\n")
    write(
        root,
        "observability/observability.yaml",
        """apiVersion: inari.dev/v1alpha1
kind: Observability
app: workflows-scaffold
folder: workflows-scaffold
datasources: {prometheus: '${DS_PROMETHEUS}'}
linkVariables: [namespace]
dashboards:
  - {title: Overview, uid: workflows-scaffold-overview, file: dashboards/overview.json}
rules:
  - {file: rules/app.yaml, evaluation: central}
targets: [central, local]
severityRouting: {critical: platform-critical}
minimumAppVersion: '>=0.1.0 <2.0.0'
observabilityPack: {package: observability-pack, versionRange: '>=0.1.0 <2.0.0'}
""",
    )
    write(
        root,
        "observability/dashboards/overview.json",
        json.dumps(
            {
                "uid": "workflows-scaffold-overview",
                "title": "Overview",
                "panels": [{"type": "timeseries", "datasource": {"type": "prometheus", "uid": "${DS_PROMETHEUS}"}}],
            }
        ),
    )
    write(root, "observability/rules/app.yaml", "groups: []\n")
    write(root, "observability/tests/alloy/config.river", "// test fixture\n")
    write(
        root,
        "tests/smoke/suite.yaml",
        """suiteSchema: inari.smoke.v1
target: {id: workflows-scaffold, version: 0.1.0, component: charts/workflows-scaffold}
compatibleAppVersions: '>=0.1.0 <2.0.0'
parameterContract: inari.smoke.params.v1
dependencies: []
timeout: 5m
profiles:
  ci: {sideEffects: syntheticWrite, cleanup: required}
  stage: {sideEffects: readOnly, cleanup: required}
  prod: {sideEffects: readOnly, cleanup: required}
rbacRequirements: [{verbs: [get], resources: [pods]}]
workflowTemplate: workflowtemplate.yaml
entrypoint: smoke
""",
    )
    write(
        root,
        "tests/smoke/workflowtemplate.yaml",
        """apiVersion: argoproj.io/v1alpha1
kind: WorkflowTemplate
metadata: {name: workflows-scaffold}
spec:
  entrypoint: smoke
  templates:
    - name: smoke
      container:
        image: ghcr.io/7k-inari/inari-cli@sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef
        command: [true]
""",
    )
    write(root, "tests/smoke/README.md", "# Smoke\n")
    write(root, "ci/compatibility-matrix.json", json.dumps({"schema": "inari.compat.v1", "entries": []}))


def use_fixture_only_smoke(root: Path) -> None:
    config = root / ".hiroba.yaml"
    config.write_text(config.read_text().replace("  targetComponent: charts/workflows-scaffold\n", ""))
    suite = root / "tests/smoke/suite.yaml"
    suite.write_text(suite.read_text().replace(
        "target: {id: workflows-scaffold, version: 0.1.0, component: charts/workflows-scaffold}",
        """target:
  id: workflows-scaffold-smoke
  version: 0.1.0
  adapter:
    kind: manifests
    path: fixtures/app
    fixtureOnly: true
    readiness:
      - {kind: Deployment, name: workflows-scaffold-fixture, namespace: default, condition: Available}
executableProfiles: [ci]""",
    ))
    write(
        root,
        "tests/smoke/fixtures/app/deployment.yaml",
        """apiVersion: apps/v1
kind: Deployment
metadata: {name: workflows-scaffold-fixture}
spec:
  template:
    spec:
      containers:
        - name: fixture
          image: ghcr.io/7k-hiroba/fixture@sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef
          securityContext: {runAsNonRoot: true}
""",
    )


class ValidateRepositoryTests(unittest.TestCase):
    def run_validation(self, mutate=None, registry: bool = True) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_valid_repo(root)
            if mutate:
                mutate(root)
            command = [str(PYTHON), str(SCRIPT), "--root", str(root)]
            if registry:
                registry_path = root / "registry.yaml"
                registry_path.write_text("apps:\n  - {name: workflows-scaffold, repository: 7K-Hiroba/workflows}\n")
                command.extend(["--registry", str(registry_path)])
            return subprocess.run(command, text=True, capture_output=True, check=False)

    def test_valid_repository_passes(self) -> None:
        result = self.run_validation()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_fixture_only_manifests_smoke_is_valid_and_ci_only(self) -> None:
        result = self.run_validation(use_fixture_only_smoke)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_fixture_only_smoke_rejects_stage_or_prod_execution(self) -> None:
        def stage_eligible(root: Path) -> None:
            use_fixture_only_smoke(root)
            suite = root / "tests/smoke/suite.yaml"
            suite.write_text(suite.read_text().replace("executableProfiles: [ci]", "executableProfiles: [ci, stage]"))
        result = self.run_validation(stage_eligible)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("executableProfiles", result.stdout + result.stderr)

    def test_fixture_only_smoke_rejects_an_artifact_component(self) -> None:
        def artifact_bound(root: Path) -> None:
            use_fixture_only_smoke(root)
            suite = root / "tests/smoke/suite.yaml"
            suite.write_text(suite.read_text().replace("  version: 0.1.0\n  adapter:", "  version: 0.1.0\n  component: charts/workflows-scaffold\n  adapter:"))
        result = self.run_validation(artifact_bound)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("fixture", (result.stdout + result.stderr).lower())

    def test_chartless_observability_passes_without_chart_config_or_outputs(self) -> None:
        def chartless(root: Path) -> None:
            config = root / ".hiroba.yaml"
            text = config.read_text().replace("  chart: charts/workflows-scaffold\n", "")
            text = text.replace("smoke:\n  path: tests/smoke\n  targetComponent: charts/workflows-scaffold\n", "")
            config.write_text(text)
            shutil.rmtree(root / "charts")
        result = self.run_validation(chartless)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_observability_chart_reference_must_exist(self) -> None:
        def missing_chart(root: Path) -> None:
            shutil.rmtree(root / "charts/workflows-scaffold")
        result = self.run_validation(missing_chart)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("chart", (result.stdout + result.stderr).lower())

    def test_rejects_invalid_package_metadata_and_unknown_type(self) -> None:
        def invalid(root: Path) -> None:
            path = root / "packages/app/package.yaml"
            path.write_text(path.read_text().replace("channel: incubating", "channel: latest").replace("type: platform-app", "type: unknown"))
        result = self.run_validation(invalid)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("channel", result.stdout + result.stderr)
        self.assertIn("type", result.stdout + result.stderr)

    def test_platform_app_requires_valid_schema_and_defaults(self) -> None:
        def invalid(root: Path) -> None:
            (root / "packages/app/values-defaults.yaml").write_text("replicas: 0\n")
        result = self.run_validation(invalid)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("values-defaults.yaml", result.stdout + result.stderr)

    def test_rejects_mutable_or_release_asset_ui_remote(self) -> None:
        def invalid(root: Path) -> None:
            path = root / "extension.yaml"
            path.write_text(path.read_text().replace("remoteEntryOci: ghcr.io/7k-hiroba/workflows-scaffold/extension-ui", "remoteEntry: https://github.com/x/y/releases/download/v1/remoteEntry.js"))
        result = self.run_validation(invalid)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("remoteEntry", result.stdout + result.stderr)

    def test_rejects_dashboard_uid_and_datasource_violations(self) -> None:
        def invalid(root: Path) -> None:
            path = root / "observability/dashboards/overview.json"
            data = json.loads(path.read_text())
            data["uid"] = "collision"
            data["panels"][0]["datasource"]["uid"] = "prometheus-prod"
            path.write_text(json.dumps(data))
        result = self.run_validation(invalid)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("dashboard", (result.stdout + result.stderr).lower())

    def test_rejects_mutating_prod_rbac_and_mutable_smoke_images(self) -> None:
        def invalid(root: Path) -> None:
            suite = root / "tests/smoke/suite.yaml"
            suite.write_text(suite.read_text().replace("prod: {sideEffects: readOnly", "prod: {sideEffects: mutating"))
            template = root / "tests/smoke/workflowtemplate.yaml"
            template.write_text(template.read_text().replace("ghcr.io/7k-inari/inari-cli@sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef", "ghcr.io/7k-inari/inari-cli:latest"))
        result = self.run_validation(invalid)
        self.assertNotEqual(result.returncode, 0)
        output = result.stdout + result.stderr
        self.assertIn("prod", output)
        self.assertIn("digest", output)

    def test_rejects_rbac_resources_in_suite(self) -> None:
        def invalid(root: Path) -> None:
            write(root, "tests/smoke/rbac.yaml", "apiVersion: rbac.authorization.k8s.io/v1\nkind: RoleBinding\n")
        result = self.run_validation(invalid)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("RBAC", result.stdout + result.stderr)

    def test_rejects_symlinked_content(self) -> None:
        def invalid(root: Path) -> None:
            os.symlink("/etc/passwd", root / "packages/app/escape")
        result = self.run_validation(invalid)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("symlink", result.stdout + result.stderr)

    def test_rejects_parent_traversal_in_component_roots_and_discovery(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_valid_repo(root)
            config = root / ".hiroba.yaml"
            config.write_text(config.read_text().replace("packagesRoot: packages", "packagesRoot: ../outside"))
            validation = subprocess.run([str(PYTHON), str(SCRIPT), "--root", str(root)], text=True, capture_output=True, check=False)
            self.assertNotEqual(validation.returncode, 0)
            self.assertIn("unsafe", (validation.stdout + validation.stderr).lower())
            discovery = subprocess.run([str(PYTHON), str(ROOT / "scripts/discover-components.py"), "--root", str(root), "--all"], text=True, capture_output=True, check=False)
            self.assertNotEqual(discovery.returncode, 0)

    def test_rejects_smoke_workflow_template_outside_suite(self) -> None:
        def invalid(root: Path) -> None:
            write(root, "outside.yaml", "apiVersion: v1\nkind: ConfigMap\n")
            suite = root / "tests/smoke/suite.yaml"
            suite.write_text(suite.read_text().replace("workflowTemplate: workflowtemplate.yaml", "workflowTemplate: ../../outside.yaml"))
        result = self.run_validation(invalid)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unsafe", (result.stdout + result.stderr).lower())

    def test_rejects_duplicate_registry_app(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_valid_repo(root)
            registry = root / "registry.yaml"
            registry.write_text("apps:\n  - {name: workflows-scaffold, repository: 7K-Hiroba/workflows}\n  - {name: workflows-scaffold, repository: 7K-Hiroba/other}\n")
            result = subprocess.run([str(PYTHON), str(SCRIPT), "--root", str(root), "--registry", str(registry)], text=True, capture_output=True, check=False)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("duplicate", (result.stdout + result.stderr).lower())


if __name__ == "__main__":
    unittest.main()
