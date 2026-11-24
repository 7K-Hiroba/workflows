from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml

from tests.unit.test_validate_repository import make_valid_repo, use_fixture_only_smoke

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/prepare-release-plan.py"


class PrepareReleasePlanTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        make_valid_repo(self.root)
        subprocess.run(["git", "init", "-b", "main", str(self.root)], check=True, capture_output=True)
        subprocess.run(["git", "-C", str(self.root), "config", "user.name", "CI"], check=True)
        subprocess.run(["git", "-C", str(self.root), "config", "user.email", "ci@example.invalid"], check=True)
        subprocess.run(["git", "-C", str(self.root), "add", "-A"], check=True)
        subprocess.run(["git", "-C", str(self.root), "commit", "-m", "fixture"], check=True, capture_output=True)
        self.sha = subprocess.check_output(["git", "-C", str(self.root), "rev-parse", "HEAD"], text=True).strip()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def run_plan(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run([str(ROOT / ".venv/bin/python"), str(SCRIPT), "--root", str(self.root), "--source-sha", self.sha, *args], text=True, capture_output=True, check=False)

    def enable_chart_lifecycle(self, chart: str = "charts/workflows-scaffold") -> None:
        name = Path(chart).name
        fixture = self.root / f"tests/chart-lifecycle/{name}"
        fixture.mkdir(parents=True, exist_ok=True)
        (fixture / "previous.tgz").write_bytes(b"previous")
        (fixture / "current.tgz").write_bytes(b"current")
        assertion = fixture / "assert.sh"
        assertion.write_text("#!/usr/bin/env bash\nexit 0\n")
        assertion.chmod(0o755)
        declaration = {
            "schema": "inari.chart-test.v1",
            "upgrade": {
                "previousPackage": f"tests/chart-lifecycle/{name}/previous.tgz",
                "currentPackage": f"tests/chart-lifecycle/{name}/current.tgz",
                "timeout": "5m",
                "assertions": f"tests/chart-lifecycle/{name}/assert.sh",
            },
        }
        path = self.root / chart / "ci/test.yaml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml.safe_dump(declaration, sort_keys=False))

    def test_chart_upgrade_adds_only_its_derived_required_lane(self) -> None:
        result = self.run_plan("--rehearsal")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        plan = json.loads(result.stdout)
        self.assertFalse(plan.get("hasChartLifecycle", False))
        self.assertFalse(any(lane.startswith("chart-lifecycle-") for lane in plan["requiredLanes"]))
        self.enable_chart_lifecycle()
        result = self.run_plan("--rehearsal")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        plan = json.loads(result.stdout)
        self.assertTrue(plan.get("hasChartLifecycle", False))
        self.assertIn("chart-lifecycle-workflows-scaffold", plan["requiredLanes"])

    def test_multiple_chart_upgrades_have_distinct_required_lanes(self) -> None:
        self.enable_chart_lifecycle()
        second = self.root / "charts/second"
        shutil.copytree(self.root / "charts/workflows-scaffold", second)
        (second / "Chart.yaml").write_text("apiVersion: v2\nname: second\nversion: 0.1.0\n")
        self.enable_chart_lifecycle("charts/second")
        result = self.run_plan("--rehearsal")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        lanes = json.loads(result.stdout)["requiredLanes"]
        self.assertIn("chart-lifecycle-workflows-scaffold", lanes)
        self.assertIn("chart-lifecycle-second", lanes)

    def test_untagged_release_includes_all_components_and_lanes(self) -> None:
        result = self.run_plan()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        plan = json.loads(result.stdout)
        self.assertEqual(len(plan["components"]), 8)
        for lane in ("validate", "package", "go", "ui", "chart", "observability", "compat", "browser", "runtime-smoke"):
            self.assertIn(lane, plan["requiredLanes"])
        self.assertTrue(plan["hasExtension"])
        self.assertTrue(plan["hasSmoke"])

    def test_single_component_release_lanes_are_independent(self) -> None:
        config_path = self.root / ".hiroba.yaml"
        for absent, expected, forbidden in (
            ("ui", {"go", "compat"}, {"ui", "browser"}),
            ("extension", {"ui", "browser"}, {"go", "compat"}),
        ):
            with self.subTest(absent=absent):
                config = yaml.safe_load(config_path.read_text())
                config["components"].pop(absent, None)
                config_path.write_text(yaml.safe_dump(config, sort_keys=False))
                result = self.run_plan("--rehearsal")
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                plan = json.loads(result.stdout)
                self.assertTrue(expected.issubset(set(plan["requiredLanes"])))
                self.assertTrue(forbidden.isdisjoint(plan["requiredLanes"]))
                self.assertEqual(plan["hasExtension"], absent != "extension")
                self.assertEqual(plan["hasUI"], absent != "ui")
                restored = yaml.safe_load(config_path.read_text())
                restored["components"][absent] = {"path": absent, "version": "0.1.0"}
                config_path.write_text(yaml.safe_dump(restored, sort_keys=False))

    def test_existing_target_tag_filters_chart_and_smoke(self) -> None:
        subprocess.run(["git", "-C", str(self.root), "tag", "workflows-scaffold-v0.1.0", self.sha], check=True)
        result = self.run_plan()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        kinds = [item["kind"] for item in json.loads(result.stdout)["components"]]
        self.assertNotIn("chart", kinds)
        self.assertNotIn("smoke", kinds)

    def test_edge_includes_all_even_when_tagged(self) -> None:
        subprocess.run(["git", "-C", str(self.root), "tag", "workflows-scaffold-v0.1.0", self.sha], check=True)
        result = self.run_plan("--edge")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(len(json.loads(result.stdout)["components"]), 8)

    def test_edge_skips_release_merges(self) -> None:
        subprocess.run(["git", "-C", str(self.root), "commit", "--allow-empty", "-m", "chore: release app 0.2.0"], check=True, capture_output=True)
        result = self.run_plan("--edge")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        plan = json.loads(result.stdout)
        self.assertFalse(plan["shouldPublish"])
        self.assertEqual(plan["publishComponents"], [])

    def test_rehearsal_publishes_all_without_finalization_components(self) -> None:
        result = self.run_plan("--rehearsal")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        plan = json.loads(result.stdout)
        self.assertEqual(plan["count"], 0)
        self.assertEqual(len(plan["publishComponents"]), 8)
        self.assertTrue(plan["rehearsal"])

    def test_repair_selects_only_matching_component_and_target_smoke(self) -> None:
        result = self.run_plan("--repair-tag", "workflows-scaffold-v0.1.0")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        plan = json.loads(result.stdout)
        self.assertEqual([item["kind"] for item in plan["components"]], ["chart", "smoke"])

    def test_opt_in_kind_qualified_identities_resolve_same_name_components(self) -> None:
        (self.root / "packages/app").rename(self.root / "packages/workflows-scaffold")
        (self.root / "templates/service").rename(self.root / "templates/workflows-scaffold")
        template = self.root / "templates/workflows-scaffold/template.yaml"
        document = yaml.safe_load(template.read_text())
        document["name"] = "workflows-scaffold"
        template.write_text(yaml.safe_dump(document, sort_keys=False))
        config_path = self.root / ".hiroba.yaml"
        config = yaml.safe_load(config_path.read_text())
        config["releaseComponents"] = {
            "charts/workflows-scaffold": "chart-workflows-scaffold",
            "packages/workflows-scaffold": "package-workflows-scaffold",
            "templates/workflows-scaffold": "template-workflows-scaffold",
        }
        config_path.write_text(yaml.safe_dump(config, sort_keys=False))

        result = self.run_plan("--rehearsal")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        components = {
            item["path"]: item
            for item in json.loads(result.stdout)["publishComponents"]
            if item["path"] in config["releaseComponents"]
        }
        self.assertEqual(set(components), set(config["releaseComponents"]))
        for path, release_component in config["releaseComponents"].items():
            self.assertEqual(components[path]["releaseComponent"], release_component)

        repair = self.run_plan("--repair-tag", "chart-workflows-scaffold-v0.1.0")
        self.assertEqual(repair.returncode, 0, repair.stdout + repair.stderr)
        self.assertEqual([item["kind"] for item in json.loads(repair.stdout)["components"]], ["chart", "smoke"])

        synchronized = subprocess.run([
            str(ROOT / ".venv/bin/python"), str(ROOT / "scripts/sync-release-please-config.py"),
            "--root", str(self.root),
        ], text=True, capture_output=True, check=False)
        self.assertEqual(synchronized.returncode, 0, synchronized.stdout + synchronized.stderr)
        release_please = json.loads((self.root / "release-please-config.json").read_text())
        for path, release_component in config["releaseComponents"].items():
            self.assertEqual(release_please["packages"][path]["component"], release_component)
        self.assertNotIn("component", release_please["packages"]["packages/admission-example"])

    def enable_standalone_smoke(self) -> None:
        use_fixture_only_smoke(self.root)
        subprocess.run(["git", "-C", str(self.root), "add", ".hiroba.yaml", "tests/smoke"], check=True)
        subprocess.run(["git", "-C", str(self.root), "commit", "-m", "standalone smoke"], check=True, capture_output=True)
        self.sha = subprocess.check_output(["git", "-C", str(self.root), "rev-parse", "HEAD"], text=True).strip()

    def test_standalone_fixture_smoke_has_independent_release_plan(self) -> None:
        self.enable_standalone_smoke()
        result = self.run_plan()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        smoke = next(item for item in json.loads(result.stdout)["components"] if item["kind"] == "smoke")
        self.assertEqual(smoke["name"], "workflows-scaffold-smoke")
        self.assertFalse(smoke["appEvidenceEligible"])

    def test_standalone_fixture_tag_filters_and_repairs_only_smoke(self) -> None:
        self.enable_standalone_smoke()
        subprocess.run(["git", "-C", str(self.root), "tag", "workflows-scaffold-smoke-v0.1.0", self.sha], check=True)
        result = self.run_plan()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("smoke", [item["kind"] for item in json.loads(result.stdout)["components"]])
        repair = self.run_plan("--repair-tag", "workflows-scaffold-smoke-v0.1.0")
        self.assertEqual(repair.returncode, 0, repair.stdout + repair.stderr)
        self.assertEqual([item["kind"] for item in json.loads(repair.stdout)["components"]], ["smoke"])

    def test_standalone_fixture_rejects_duplicate_final_tag(self) -> None:
        self.enable_standalone_smoke()
        package = self.root / "packages/workflows-scaffold-smoke"
        (package / "tests").mkdir(parents=True)
        (package / "package.yaml").write_text("version: 0.1.0\nchannel: incubating\ntype: policy-pack\ndescription: collision\ncategory: test\n")
        (package / "policies.yaml").write_text("apiVersion: admissionregistration.k8s.io/v1\nkind: ValidatingAdmissionPolicy\n")
        (package / "README.md").write_text("# collision\n")
        (package / "tests/run.sh").write_text("#!/usr/bin/env bash\nexit 0\n")
        subprocess.run(["git", "-C", str(self.root), "add", "packages/workflows-scaffold-smoke"], check=True)
        subprocess.run(["git", "-C", str(self.root), "commit", "-m", "tag collision"], check=True, capture_output=True)
        self.sha = subprocess.check_output(["git", "-C", str(self.root), "rev-parse", "HEAD"], text=True).strip()
        for args in ((), ("--repair-tag", "workflows-scaffold-smoke-v0.1.0")):
            with self.subTest(args=args):
                result = self.run_plan(*args)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("duplicate", (result.stdout + result.stderr).lower())

    def test_standalone_fixture_change_requires_own_version_bump(self) -> None:
        self.enable_standalone_smoke()
        subprocess.run(["git", "-C", str(self.root), "tag", "workflows-scaffold-smoke-v0.1.0", self.sha], check=True)
        changed = self.root / "changed.txt"
        changed.write_text("tests/smoke/suite.yaml\n")
        result = self.run_plan("--changed-files", str(changed))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("version bump", (result.stdout + result.stderr).lower())

    def test_smoke_only_change_requires_target_version_bump(self) -> None:
        subprocess.run(["git", "-C", str(self.root), "tag", "workflows-scaffold-v0.1.0", self.sha], check=True)
        changed = self.root / "changed.txt"
        changed.write_text("tests/smoke/suite.yaml\n")
        result = self.run_plan("--changed-files", str(changed))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("target", (result.stdout + result.stderr).lower())


class NonPluginRehearsalPlanTests(unittest.TestCase):
    def test_real_fixture_has_distinct_final_tags_and_a_viable_publish_plan(self) -> None:
        root = ROOT / "tests/fixtures/non-plugin-runtime"
        result = subprocess.run([
            str(ROOT / ".venv/bin/python"), str(SCRIPT), "--root", str(root),
            "--source-sha", "c3bdc1e715391a8c66d599ce32356e6ea071e169", "--rehearsal",
        ], text=True, capture_output=True, check=False)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        plan = json.loads(result.stdout)
        self.assertTrue(plan["rehearsal"])
        self.assertTrue(plan["shouldPublish"])
        self.assertEqual(plan["components"], [])
        components = {item["kind"]: item for item in plan["publishComponents"]}
        self.assertEqual(set(components), {"chart", "package", "smoke"})
        self.assertEqual(components["chart"]["path"], "charts/hiroba-nonplugin-smoke")
        self.assertEqual(components["package"]["path"], "packages/hiroba-nonplugin-package")
        self.assertEqual(components["smoke"]["targetComponent"], components["chart"]["path"])

        tags = {kind: f"{item['name']}-v{item['version']}" for kind, item in components.items()}
        self.assertEqual(tags["chart"], "hiroba-nonplugin-smoke-v0.1.0")
        self.assertEqual(tags["package"], "hiroba-nonplugin-package-v0.1.0")
        self.assertEqual(tags["smoke"], tags["chart"], "artifact-bound smoke shares only its target chart release")
        self.assertNotEqual(tags["chart"], tags["package"])
        self.assertTrue(plan["hasChart"])
        self.assertTrue(plan["hasPackages"])
        self.assertTrue(plan["hasSmoke"])
        self.assertEqual(plan["requiredLanes"], ["validate", "package", "chart", "runtime-smoke"])

        config = json.loads((root / "release-please-config.json").read_text())
        manifest = json.loads((root / ".release-please-manifest.json").read_text())
        self.assertTrue(config["include-component-in-tag"])
        self.assertEqual(config["tag-separator"], "-v")
        self.assertEqual(set(config["packages"]), {components["chart"]["path"], components["package"]["path"]})
        self.assertEqual(set(manifest), set(config["packages"]))
        for script in ("build-indexes.py", "sync-release-please-config.py"):
            checked = subprocess.run([
                str(ROOT / ".venv/bin/python"), str(ROOT / "scripts" / script), "--root", str(root), "--check",
            ], text=True, capture_output=True, check=False)
            self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)

        suite = yaml.safe_load((root / "tests/smoke/suite.yaml").read_text())
        self.assertEqual(suite["target"]["component"], components["chart"]["path"])
        self.assertEqual(suite["target"]["adapter"]["kind"], "helm")
        self.assertFalse(suite["target"]["adapter"]["fixtureOnly"])
        package_chart = yaml.safe_load((root / components["package"]["path"] / "chart.yaml").read_text())
        self.assertEqual(package_chart["chart"], components["chart"]["name"])


if __name__ == "__main__":
    unittest.main()
