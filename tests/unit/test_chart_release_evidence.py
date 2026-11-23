from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/chart-release-evidence.py"
PYTHON = ROOT / ".venv/bin/python"


class ChartReleaseEvidenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.make_config("stack")
        self.make_fixture_suite()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def write(self, relative: str, content: str, executable: bool = False) -> None:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        if executable:
            path.chmod(0o755)

    def make_config(self, archetype: str, declaration: bool = True) -> None:
        stack = "stackTest: {path: tests/stack}\n" if declaration else ""
        self.write(".hiroba.yaml", f"""schema: inari.hiroba.app.v2
app: example
archetype: {archetype}
trustTier: experimental
components: {{chartsRoot: charts, packagesRoot: packages, templatesRoot: templates}}
{stack}""")

    def make_fixture_suite(self) -> None:
        self.write("tests/stack/suite.yaml", """schema: inari.stack-test.v1
setupProfiles: []
covers: []
fixtureOnly: true
install: {script: install.sh, timeout: 5m}
upgrade: {script: upgrade.sh, timeout: 5m}
""")
        for name in ("install.sh", "upgrade.sh"):
            self.write("tests/stack/" + name, "#!/usr/bin/env bash\nexit 0\n", executable=True)

    def run_policy(self, standalone: str = "true", lanes: str = "chart") -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(PYTHON), str(SCRIPT), "--root", str(self.root), "--standalone", standalone, "--required-lanes", lanes],
            text=True,
            capture_output=True,
            check=False,
        )

    def test_standalone_stack_adds_mandatory_lifecycle_lane(self) -> None:
        result = self.run_policy()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        plan = json.loads(result.stdout)
        self.assertTrue(plan["hasStackTest"])
        self.assertEqual(plan["requiredLanes"], "chart stack-lifecycle")

    def test_standalone_non_stack_does_not_add_lane(self) -> None:
        self.make_config("non-stack", declaration=False)
        result = self.run_policy()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        plan = json.loads(result.stdout)
        self.assertFalse(plan["hasStackTest"])
        self.assertEqual(plan["requiredLanes"], "chart")

    def test_coordinated_release_preserves_normalized_evidence_input(self) -> None:
        result = self.run_policy(standalone="false")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        plan = json.loads(result.stdout)
        self.assertTrue(plan["hasStackTest"])
        self.assertEqual(plan["requiredLanes"], "chart")

    def test_existing_lifecycle_lane_is_not_duplicated(self) -> None:
        result = self.run_policy(lanes="chart stack-lifecycle")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout)["requiredLanes"], "chart stack-lifecycle")

    def test_invalid_or_empty_lane_input_fails_closed(self) -> None:
        for lanes in ("", "chart;rm"):
            with self.subTest(lanes=lanes):
                result = self.run_policy(lanes=lanes)
                self.assertNotEqual(result.returncode, 0)

    def test_missing_stack_declaration_fails_before_policy_output(self) -> None:
        self.make_config("stack", declaration=False)
        result = self.run_policy()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("stackTest", result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
