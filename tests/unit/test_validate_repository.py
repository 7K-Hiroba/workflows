from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml

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
metadata:
  name: observability-pack
  annotations: {inari.dev/observability-render-contract: inari.observability-pack/v2}
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
    config_path = root / ".hiroba.yaml"
    config = yaml.safe_load(config_path.read_text())
    config["smoke"].pop("targetComponent", None)
    config_path.write_text(yaml.safe_dump(config, sort_keys=False))
    suite_path = root / "tests/smoke/suite.yaml"
    suite = yaml.safe_load(suite_path.read_text())
    suite["target"] = {
        "id": "workflows-scaffold-smoke",
        "version": "0.1.0",
        "adapter": {
            "kind": "manifests",
            "path": "fixtures/app",
            "fixtureOnly": True,
            "readiness": [{"kind": "Deployment", "name": "workflows-scaffold-fixture", "namespace": "default", "condition": "Available"}],
        },
    }
    suite["executableProfiles"] = ["ci"]
    suite_path.write_text(yaml.safe_dump(suite, sort_keys=False))
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
    def run_validation(self, mutate=None, registry: bool = True, community_registry: bool = False) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_valid_repo(root)
            if mutate:
                mutate(root)
            command = [str(PYTHON), str(SCRIPT), "--root", str(root)]
            if registry:
                registry_path = root / "registry.yaml"
                identity = "id" if community_registry else "name"
                registry_path.write_text(f"apps:\n  - {{{identity}: workflows-scaffold, repository: 7K-Hiroba/workflows}}\n")
                command.extend(["--registry", str(registry_path)])
            return subprocess.run(command, text=True, capture_output=True, check=False)

    def test_valid_repository_passes(self) -> None:
        result = self.run_validation()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_generic_kro_rgd_does_not_need_observability_pack_annotation(self) -> None:
        def generic(root: Path) -> None:
            package = root / "packages/monitoring-stack"
            package.mkdir()
            (package / "package.yaml").write_text("version: 1.0.0\nchannel: incubating\ntype: kro-rgd\ncategory: observability\ndescription: Generic stack\n")
            (package / "ui-hints.yaml").write_text("fields: []\n")
            (package / "README.md").write_text("Generic stack\n")
            (package / "tests").mkdir()
            (package / "tests/run.sh").write_text("#!/bin/sh\nexit 0\n")
            (package / "rgd.yaml").write_text("apiVersion: kro.run/v1alpha1\nkind: ResourceGraphDefinition\nspec:\n  schema: {kind: MonitoringStack}\n  resources: []\n")
        result = self.run_validation(generic)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_registry_accepts_community_id_field(self) -> None:
        result = self.run_validation(community_registry=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_rejects_legacy_observability_pack_contract(self) -> None:
        def legacy(root: Path) -> None:
            rgd = root / "packages/observability-pack/rgd.yaml"
            rgd.write_text(rgd.read_text().replace("inari.observability-pack/v2", "inari.observability-pack/v1"))
        result = self.run_validation(legacy)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("inari.observability-pack/v2", result.stdout + result.stderr)

    def test_rejects_ambiguous_v2_rule_gates(self) -> None:
        def ambiguous(root: Path) -> None:
            rgd = root / "packages/observability-pack/rgd.yaml"
            rgd.write_text(rgd.read_text() + '''  - id: rulesCentral
    template:
      apiVersion: monitoring.coreos.com/v1
      kind: PrometheusRule
      metadata: {name: workflows-scaffold-central}
    includeWhen: [${schema.spec.render == "all"}]
''')
        result = self.run_validation(ambiguous)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("rulesCentral", result.stdout + result.stderr)

    def test_rule_include_when_requires_exact_canonical_form(self) -> None:
        for evaluation, boolean in (("central", "rulesCentral"), ("local", "rulesLocal")):
            resource_id = "rules" + evaluation.capitalize()
            invalid_expressions = (
                f'${{schema.spec.render == "rules-{evaluation}" || schema.spec.{boolean}}}',
                f'${{schema.spec.render == "dashboards" && schema.spec.{boolean}}}',
                f'${{schema.spec.render == "rules-{evaluation}" && schema.spec.{boolean}}}',
            )
            for expression in invalid_expressions:
                with self.subTest(evaluation=evaluation, expression=expression):
                    def invalid(root: Path, expression=expression, resource_id=resource_id) -> None:
                        rgd_path = root / "packages/observability-pack/rgd.yaml"
                        document = yaml.safe_load(rgd_path.read_text())
                        document["spec"]["resources"].append({
                            "id": resource_id,
                            "template": {
                                "apiVersion": "monitoring.coreos.com/v1",
                                "kind": "PrometheusRule",
                                "metadata": {"name": f"workflows-scaffold-{evaluation}"},
                            },
                            "includeWhen": [expression],
                        })
                        rgd_path.write_text(yaml.safe_dump(document, sort_keys=False))
                    result = self.run_validation(invalid)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn(boolean, result.stdout + result.stderr)

    def test_canonical_rule_include_when_is_valid(self) -> None:
        def canonical(root: Path) -> None:
            rgd_path = root / "packages/observability-pack/rgd.yaml"
            document = yaml.safe_load(rgd_path.read_text())
            for evaluation, boolean in (("central", "rulesCentral"), ("local", "rulesLocal")):
                resource_id = "rules" + evaluation.capitalize()
                expression = f'${{(schema.spec.render == "all" || schema.spec.render == "rules-{evaluation}") && schema.spec.{boolean}}}'
                document["spec"]["resources"].append({
                    "id": resource_id,
                    "template": {
                        "apiVersion": "monitoring.coreos.com/v1",
                        "kind": "PrometheusRule",
                        "metadata": {"name": f"workflows-scaffold-{evaluation}"},
                    },
                    "includeWhen": [expression],
                })
            rgd_path.write_text(yaml.safe_dump(document, sort_keys=False))
        result = self.run_validation(canonical)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_observability_package_requires_full_metadata(self) -> None:
        def missing_metadata(root: Path) -> None:
            package = root / "packages/app/package.yaml"
            package.write_text(package.read_text() + "observability:\n  package: observability-pack\n  versionRange: '>=0.1.0 <2.0.0'\n")
        result = self.run_validation(missing_metadata)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("observability.yaml", result.stdout + result.stderr)

    def test_component_template_observability_manifest_is_valid(self) -> None:
        def component(root: Path) -> None:
            template = root / "templates/service/template.yaml"
            template.write_text(template.read_text() + "observability:\n  manifest: observability/observability.yaml\n")
            write(root, "templates/service/observability/observability.yaml", "apiVersion: inari.dev/v1alpha1\nkind: Observability\napp: workflows-scaffold\nfolder: workflows-scaffold\ndatasources: {prometheus: '${DS_PROMETHEUS}'}\ndashboards: [{title: Overview, uid: workflows-scaffold-overview, file: dashboards/overview.json}]\nrules: [{file: rules/app.yaml, evaluation: central}]\ntargets: [central, local]\nseverityRouting: {critical: platform-security}\nminimumAppVersion: '>=0.1.0 <2.0.0'\nobservabilityPack: {package: observability-pack, versionRange: '>=0.1.0 <2.0.0'}\n")
            write(root, "templates/service/observability/dashboards/overview.json", json.dumps({"uid": "workflows-scaffold-overview", "title": "Overview", "panels": [{"datasource": {"uid": "${DS_PROMETHEUS}"}}]}))
        result = self.run_validation(component)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_template_observability_declaration_must_be_component_and_confined(self) -> None:
        def invalid(root: Path) -> None:
            template = root / "templates/service/template.yaml"
            template.write_text(template.read_text().replace("kind: component", "kind: gitops-repo") + "observability:\n  manifest: observability/observability.yaml\n")
            write(root, "templates/service/observability/observability.yaml", "kind: Observability\n")
        result = self.run_validation(invalid)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("component", (result.stdout + result.stderr).lower())

    def test_template_observability_manifest_must_exist_inside_template(self) -> None:
        def invalid(root: Path) -> None:
            template = root / "templates/service/template.yaml"
            template.write_text(template.read_text() + "observability:\n  manifest: ../../outside.yaml\n")
        result = self.run_validation(invalid)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("unsafe", (result.stdout + result.stderr).lower())

    def test_manifests_package_is_valid(self) -> None:
        def add_manifests(root: Path) -> None:
            write(root, "packages/plain/package.yaml", "version: 0.1.0\nchannel: incubating\ntype: manifests\ndescription: Plain manifests\ncategory: test\n")
            write(root, "packages/plain/manifests.yaml", "apiVersion: v1\nkind: ConfigMap\nmetadata: {name: plain}\n")
            write(root, "packages/plain/README.md", "# plain\n")
            write(root, "packages/plain/tests/run.sh", "#!/usr/bin/env bash\nexit 0\n")
        result = self.run_validation(add_manifests)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_fixture_only_manifests_smoke_is_valid_and_ci_only(self) -> None:
        result = self.run_validation(use_fixture_only_smoke)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_artifact_bound_manifests_smoke_is_valid(self) -> None:
        def artifact_bound(root: Path) -> None:
            use_fixture_only_smoke(root)
            config_path = root / ".hiroba.yaml"
            config = yaml.safe_load(config_path.read_text())
            config["smoke"]["targetComponent"] = "packages/observability-pack"
            config_path.write_text(yaml.safe_dump(config, sort_keys=False))
            suite_path = root / "tests/smoke/suite.yaml"
            suite = yaml.safe_load(suite_path.read_text())
            suite["target"]["component"] = "packages/observability-pack"
            suite["target"]["adapter"]["fixtureOnly"] = False
            suite["target"]["adapter"].pop("path")
            suite["target"]["adapter"]["artifactPath"] = "rgd.yaml"
            suite["executableProfiles"] = ["ci", "stage", "prod"]
            suite_path.write_text(yaml.safe_dump(suite, sort_keys=False))
        result = self.run_validation(artifact_bound)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_fixture_only_smoke_rejects_stage_or_prod_execution(self) -> None:
        def stage_eligible(root: Path) -> None:
            use_fixture_only_smoke(root)
            suite_path = root / "tests/smoke/suite.yaml"
            suite = yaml.safe_load(suite_path.read_text())
            suite["executableProfiles"] = ["ci", "stage"]
            suite_path.write_text(yaml.safe_dump(suite, sort_keys=False))
        result = self.run_validation(stage_eligible)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("executableProfiles", result.stdout + result.stderr)

    def test_fixture_only_smoke_rejects_an_artifact_component(self) -> None:
        def artifact_bound(root: Path) -> None:
            use_fixture_only_smoke(root)
            suite_path = root / "tests/smoke/suite.yaml"
            suite = yaml.safe_load(suite_path.read_text())
            suite["target"]["component"] = "charts/workflows-scaffold"
            suite_path.write_text(yaml.safe_dump(suite, sort_keys=False))
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

    def test_chartless_observability_rejects_stale_generated_chart_output(self) -> None:
        def stale_output(root: Path) -> None:
            config = root / ".hiroba.yaml"
            config.write_text(config.read_text().replace("  chart: charts/workflows-scaffold\n", ""))
            write(root, "charts/workflows-scaffold/inari/observability.yaml", "# GENERATED by scripts/render-observability.py; DO NOT EDIT.\nkind: Observability\n")
        result = self.run_validation(stale_output)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("stale", (result.stdout + result.stderr).lower())

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
