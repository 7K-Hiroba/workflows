from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
PYTHON = ROOT / ".venv/bin/python"
if not PYTHON.exists():
    PYTHON = Path("python3")
CONFIG_SCRIPT = ROOT / "scripts/stack-test-config.py"
DISCOVERY_SCRIPT = ROOT / "scripts/discover-components.py"


def write(root: Path, relative: str, content: str, executable: bool = False) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    if executable:
        path.chmod(0o755)


class StackTestingContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.make_config("stack", with_stack=True)
        self.write_component("charts/example", "chart")
        self.write_component("packages/example", "kro-rgd")
        self.write_suite()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def make_config(self, archetype: str | None, with_stack: bool, schema: str = "inari.hiroba.app.v2") -> None:
        lines = [f"schema: {schema}", "app: example", "trustTier: experimental"]
        if archetype is not None:
            lines.append(f"archetype: {archetype}")
        lines.extend([
            "components:",
            "  chartsRoot: charts",
            "  packagesRoot: packages",
            "  templatesRoot: templates",
        ])
        if with_stack:
            lines.append("stackTest: {path: tests/stack}")
        write(self.root, ".hiroba.yaml", "\n".join(lines) + "\n")

    def write_component(self, relative: str, kind: str) -> None:
        if kind == "chart":
            write(self.root, relative + "/Chart.yaml", "apiVersion: v2\nname: example\nversion: 0.1.0\n")
        else:
            write(self.root, relative + "/package.yaml", "version: 0.1.0\nchannel: incubating\ntype: kro-rgd\n")

    def write_suite(self, upgrade: bool = True, covers: list[str] | None = None, fixture_only: bool = False) -> None:
        suite = {
            "schema": "inari.stack-test.v1",
            "setupProfiles": ["kro"],
            "covers": ["charts/example", "packages/example"] if covers is None else covers,
            "install": {"script": "install.sh", "timeout": "5m"},
            "diagnostics": "diagnostics.sh",
        }
        if upgrade:
            suite["upgrade"] = {"script": "upgrade.sh", "timeout": "5m"}
        if fixture_only:
            suite["fixtureOnly"] = True
        write(self.root, "tests/stack/suite.yaml", yaml.safe_dump(suite, sort_keys=False))
        for script in ("install.sh", "upgrade.sh", "diagnostics.sh"):
            write(self.root, "tests/stack/" + script, "#!/usr/bin/env bash\nexit 0\n", executable=True)

    def run_config(self) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(PYTHON), str(CONFIG_SCRIPT), "--root", str(self.root)],
            text=True,
            capture_output=True,
            check=False,
        )

    def test_stack_declaration_emits_enabled_plan(self) -> None:
        result = self.run_config()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        plan = json.loads(result.stdout)
        self.assertTrue(plan["enabled"])
        self.assertEqual(plan["archetype"], "stack")
        self.assertEqual(plan["path"], "tests/stack")
        self.assertEqual(plan["covers"], ["charts/example", "packages/example"])
        self.assertEqual(plan["setupProfiles"], ["kro"])
        self.assertIn("cacheKey", plan)

    def test_non_stack_with_components_explicitly_disables_lane(self) -> None:
        self.make_config("non-stack", with_stack=False)
        result = self.run_config()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        plan = json.loads(result.stdout)
        self.assertFalse(plan["enabled"])
        self.assertEqual(plan["archetype"], "non-stack")
        self.assertEqual(plan["covers"], [])

    def test_fixture_only_stack_has_no_component_coverage(self) -> None:
        (self.root / "charts").rename(self.root / "unused-charts")
        (self.root / "packages").rename(self.root / "unused-packages")
        self.write_suite(covers=[], fixture_only=True)
        result = self.run_config()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        plan = json.loads(result.stdout)
        self.assertTrue(plan["fixtureOnly"])
        self.assertEqual(plan["covers"], [])

    def test_discovery_marks_covered_components_without_publishing_suite(self) -> None:
        result = subprocess.run([str(PYTHON), str(DISCOVERY_SCRIPT), "--root", str(self.root), "--all"], text=True, capture_output=True, check=False)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        plan = json.loads(result.stdout)
        self.assertEqual(plan["archetype"], "stack")
        self.assertTrue(plan["hasStackTest"])
        self.assertEqual(plan["stackTest"]["path"], "tests/stack")
        self.assertTrue(all(component["stackCovered"] for component in plan["components"]))
        self.assertFalse(any(component["kind"] == "stackTest" for component in plan["components"]))

    def test_missing_archetype_fails_before_discovery(self) -> None:
        self.make_config(None, with_stack=False)
        for script in (CONFIG_SCRIPT, DISCOVERY_SCRIPT):
            with self.subTest(script=script.name):
                result = subprocess.run([str(PYTHON), str(script), "--root", str(self.root)], text=True, capture_output=True, check=False)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("archetype", result.stdout + result.stderr)

    def test_v1_config_is_rejected_by_new_contract(self) -> None:
        self.make_config("stack", with_stack=True, schema="inari.hiroba.app.v1")
        result = self.run_config()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("inari.hiroba.app.v2", result.stdout + result.stderr)

    def test_stack_without_declaration_fails(self) -> None:
        self.make_config("stack", with_stack=False)
        result = self.run_config()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("stackTest", result.stdout + result.stderr)

    def test_non_stack_with_declaration_fails(self) -> None:
        self.make_config("non-stack", with_stack=True)
        result = self.run_config()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("non-stack", result.stdout + result.stderr)

    def test_missing_upgrade_fails(self) -> None:
        self.write_suite(upgrade=False)
        result = self.run_config()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("upgrade", result.stdout + result.stderr)

    def test_incomplete_coverage_fails(self) -> None:
        self.write_component("charts/other", "chart")
        result = self.run_config()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("charts/other", result.stdout + result.stderr)

    def run_release_plan(self) -> subprocess.CompletedProcess[str]:
        config = yaml.safe_load((self.root / ".hiroba.yaml").read_text())
        config["releaseComponents"] = {"charts/example": "chart-example", "packages/example": "package-example"}
        (self.root / ".hiroba.yaml").write_text(yaml.safe_dump(config, sort_keys=False))
        if not (self.root / ".git").exists():
            subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        return subprocess.run([
            str(PYTHON), str(ROOT / "scripts/prepare-release-plan.py"),
            "--root", str(self.root), "--source-sha", "a" * 40, "--rehearsal",
        ], text=True, capture_output=True, check=False)

    def test_stack_release_requires_lifecycle_evidence(self) -> None:
        result = self.run_release_plan()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        plan = json.loads(result.stdout)
        self.assertTrue(plan["hasStackTest"])
        self.assertIn("stack-lifecycle", plan["requiredLanes"])

    def test_non_stack_release_does_not_require_lifecycle_evidence(self) -> None:
        self.make_config("non-stack", with_stack=False)
        result = self.run_release_plan()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        plan = json.loads(result.stdout)
        self.assertFalse(plan["hasStackTest"])
        self.assertNotIn("stack-lifecycle", plan["requiredLanes"])

    def test_cache_key_changes_with_selected_pin_content(self) -> None:
        first = self.run_config()
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
        key = json.loads(first.stdout)["cacheKey"]
        self.write_suite()
        second = self.run_config()
        self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
        self.assertEqual(key, json.loads(second.stdout)["cacheKey"])
        self.assertRegex(key, r"^[0-9a-f]{64}$")


if __name__ == "__main__":
    unittest.main()
