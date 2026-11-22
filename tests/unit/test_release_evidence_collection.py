from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
COLLECT = ROOT / "scripts/collect-release-evidence.py"
BUILD = ROOT / "scripts/build-test-evidence.py"
SOURCE = "a" * 40
DIGEST = "sha256:" + "b" * 64


class ReleaseEvidenceCollectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.evidence = self.root / "evidence"
        self.evidence.mkdir()
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        (self.evidence / "compat-report.json").write_text(json.dumps({
            "schema": "inari.compat-report.v1",
            "sourceSha": SOURCE,
            "completedAt": now,
            "status": "passed",
            "entries": [{"status": "passed"}],
        }))

    def tearDown(self) -> None:
        self.temp.cleanup()

    def collect(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run([
            "python3", str(COLLECT), "--evidence-dir", str(self.evidence),
            "--source-sha", SOURCE, "--required-lanes", "validate compat",
            "--lane", "validate=success", *args,
        ], text=True, capture_output=True, check=False)

    def test_collects_workflow_results_and_builds_release_predicate(self) -> None:
        result = self.collect()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        lane = json.loads((self.evidence / "validate.json").read_text())
        self.assertEqual(lane["status"], "passed")
        self.assertFalse((self.evidence / "compat.json").exists())
        predicate = self.root / "predicate.json"
        built = subprocess.run([
            "python3", str(BUILD), "--evidence-dir", str(self.evidence), "--output", str(predicate),
            "--app", "app", "--component", "app", "--trust-tier", "reviewed",
            "--source-repository", "7K-Hiroba/app", "--source-sha", SOURCE,
            "--workflow-sha", "c" * 40, "--workflow-path", ".github/workflows/release-oci.yml",
            "--run-id", "1", "--run-attempt", "1", "--artifact-repository", "ghcr.io/7k-hiroba/app/catalog/app",
            "--artifact-digest", DIGEST, "--media-type", "application/vnd.inari.catalog.package.v1+yaml",
            "--release-tag", "app-v1.0.0", "--required-lane", "validate", "--required-lane", "compat",
        ], text=True, capture_output=True, check=False)
        self.assertEqual(built.returncode, 0, built.stdout + built.stderr)
        self.assertEqual(json.loads(predicate.read_text())["sourceSha"], SOURCE)

    def test_compatibility_artifact_download_preserves_required_lane_layout(self) -> None:
        compat = yaml.safe_load((ROOT / ".github/workflows/compat-check.yml").read_text())
        upload = next(step for step in compat["jobs"]["test"]["steps"] if step.get("with", {}).get("name") == "compatibility-evidence")
        self.assertEqual(upload["with"]["path"].splitlines(), [
            "${{ needs.plan.outputs.consumer-root }}/evidence",
            "${{ needs.plan.outputs.consumer-root }}/diagnostics",
        ])
        release = yaml.safe_load((ROOT / ".github/workflows/release.yml").read_text())
        download = next(step for step in release["jobs"]["evidence"]["steps"] if step.get("with", {}).get("name") == "compatibility-evidence")
        collect = next(step for step in release["jobs"]["evidence"]["steps"] if step.get("id") == "collect")
        self.assertIn("--evidence-dir evidence", collect["run"])
        self.assertIn('cp runtime-smoke-evidence/evidence/runtime-smoke.json evidence/runtime-smoke.json', collect["run"])
        self.assertNotIn('--lane "runtime-smoke=${RUNTIME:-failure}"', collect["run"])

        artifact = self.root / "artifact"
        artifact_evidence = artifact / "evidence"
        artifact_diagnostics = artifact / "diagnostics"
        artifact_evidence.mkdir(parents=True)
        artifact_diagnostics.mkdir()
        shutil.copyfile(self.evidence / "compat-report.json", artifact_evidence / "compat-report.json")
        (artifact_evidence / "browser-report.json").write_text(json.dumps({
            "schema": "inari.browser-report.v1",
            "status": "passed",
            "sourceSha": SOURCE,
            "uiHostSha": "d" * 40,
        }))
        (artifact_evidence / "playwright-report.json").write_text("{}")
        (artifact_diagnostics / "ui-host.log").write_text("browser diagnostics\n")

        workspace = self.root / "workspace"
        workspace.mkdir()
        shutil.copytree(artifact, workspace / download["with"]["path"], dirs_exist_ok=True)
        result = subprocess.run([
            "python3", str(COLLECT), "--evidence-dir", str(workspace / "evidence"),
            "--source-sha", SOURCE, "--required-lanes", "validate compat browser runtime-smoke",
            "--lane", "validate=success", "--lane", "runtime-smoke=success",
        ], text=True, capture_output=True, check=False)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("release evidence passed: browser, compat, runtime-smoke, validate", result.stdout)
        self.assertTrue((workspace / "diagnostics/ui-host.log").is_file())

    def test_rejects_duplicate_compat_and_missing_or_failed_required_lanes(self) -> None:
        duplicate = self.collect("--lane", "compat=success")
        self.assertNotEqual(duplicate.returncode, 0)
        self.assertIn("duplicate", (duplicate.stdout + duplicate.stderr).lower())
        (self.evidence / "compat-report.json").unlink()
        (self.evidence / "compat.json").unlink()
        missing = self.collect()
        self.assertNotEqual(missing.returncode, 0)
        self.assertIn("missing required", (missing.stdout + missing.stderr).lower())

    def test_failed_workflow_result_is_not_normalized_to_passed(self) -> None:
        (self.evidence / "compat-report.json").unlink()
        result = subprocess.run([
            "python3", str(COLLECT), "--evidence-dir", str(self.evidence),
            "--source-sha", SOURCE, "--required-lanes", "validate", "--lane", "validate=failure",
        ], text=True, capture_output=True, check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(json.loads((self.evidence / "validate.json").read_text())["status"], "failed")


if __name__ == "__main__":
    unittest.main()
