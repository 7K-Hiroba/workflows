from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

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

    def test_untagged_release_includes_all_components_and_lanes(self) -> None:
        result = self.run_plan()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        plan = json.loads(result.stdout)
        self.assertEqual(len(plan["components"]), 8)
        for lane in ("validate", "package", "go", "ui", "chart", "observability", "compat", "browser", "runtime-smoke"):
            self.assertIn(lane, plan["requiredLanes"])
        self.assertTrue(plan["hasExtension"])
        self.assertTrue(plan["hasSmoke"])

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


if __name__ == "__main__":
    unittest.main()
