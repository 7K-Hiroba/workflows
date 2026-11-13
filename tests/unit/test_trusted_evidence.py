from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/build-test-evidence.py"
VERIFY = ROOT / "scripts/verify-test-evidence.py"
SOURCE = "a" * 40
WORKFLOW = "b" * 40
DIGEST = "sha256:" + "c" * 64


class TrustedEvidenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.evidence = self.root / "evidence"
        self.evidence.mkdir()
        (self.evidence / "validate.json").write_text(json.dumps({"schema": "inari.lane-result.v1", "lane": "validate", "status": "passed"}))
        (self.evidence / "runtime.json").write_text(json.dumps({"schema": "inari.lane-result.v1", "lane": "runtime", "status": "passed"}))
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        (self.evidence / "compat-report.json").write_text(json.dumps({"schema": "inari.compat-report.v1", "status": "passed", "sourceSha": SOURCE, "completedAt": now, "entries": [{"status": "passed"}]}))
        self.output = self.root / "predicate.json"

    def tearDown(self) -> None:
        self.temp.cleanup()

    def run_build(self, *extra: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run([
            "python3", str(SCRIPT), "--evidence-dir", str(self.evidence), "--output", str(self.output),
            "--app", "workflows-scaffold", "--component", "app", "--trust-tier", "reviewed",
            "--source-repository", "7K-Hiroba/workflows-scaffold", "--source-sha", SOURCE, "--workflow-sha", WORKFLOW,
            "--workflow-path", ".github/workflows/release-oci.yml", "--run-id", "123", "--run-attempt", "1",
            "--artifact-repository", "ghcr.io/7k-hiroba/workflows-scaffold/catalog/app", "--artifact-digest", DIGEST,
            "--media-type", "application/vnd.inari.catalog.package.v1+yaml", "--release-tag", "app-v0.1.0",
            "--required-lane", "validate", "--required-lane", "runtime", *extra,
        ], text=True, capture_output=True, check=False)

    def test_builds_bound_release_evidence(self) -> None:
        result = self.run_build()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        predicate = json.loads(self.output.read_text())
        self.assertEqual(predicate["schema"], "inari.test-evidence.v1")
        self.assertEqual(predicate["sourceSha"], SOURCE)
        self.assertEqual(predicate["producer"]["workflowSha"], WORKFLOW)
        self.assertEqual(predicate["artifact"]["digest"], DIGEST)
        self.assertEqual(predicate["releaseTag"], "app-v0.1.0")
        self.assertEqual([lane["lane"] for lane in predicate["lanes"]], ["compat", "runtime", "validate"])
        self.assertEqual(len(predicate["evidenceDigest"]), 64)
        verified = subprocess.run(["python3", str(VERIFY), "--predicate", str(self.output), "--source-sha", SOURCE, "--workflow-path", ".github/workflows/release-oci.yml", "--artifact-digest", DIGEST, "--release-tag", "app-v0.1.0"], text=True, capture_output=True, check=False)
        self.assertEqual(verified.returncode, 0, verified.stdout + verified.stderr)

    def test_rejects_failed_or_missing_required_lane(self) -> None:
        (self.evidence / "runtime.json").write_text(json.dumps({"schema": "inari.lane-result.v1", "lane": "runtime", "status": "failed"}))
        self.assertNotEqual(self.run_build().returncode, 0)
        (self.evidence / "runtime.json").write_text(json.dumps({"schema": "inari.lane-result.v1", "lane": "runtime", "status": "passed"}))
        (self.evidence / "validate.json").unlink()
        self.assertNotEqual(self.run_build().returncode, 0)

    def test_rejects_stale_or_unrelated_compat(self) -> None:
        stale = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat().replace("+00:00", "Z")
        (self.evidence / "compat-report.json").write_text(json.dumps({"schema": "inari.compat-report.v1", "status": "passed", "sourceSha": SOURCE, "completedAt": stale, "entries": [{"status": "passed"}]}))
        self.assertNotEqual(self.run_build().returncode, 0)
        (self.evidence / "compat-report.json").write_text(json.dumps({"schema": "inari.compat-report.v1", "status": "passed", "sourceSha": "d" * 40, "completedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"), "entries": [{"status": "passed"}]}))
        self.assertNotEqual(self.run_build().returncode, 0)

    def test_rejects_unexpected_producer_and_mismatched_verification(self) -> None:
        result = self.run_build("--workflow-path", ".github/workflows/untrusted.yml")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.run_build().returncode, 0)
        verified = subprocess.run(["python3", str(VERIFY), "--predicate", str(self.output), "--source-sha", "d" * 40, "--workflow-path", ".github/workflows/release-oci.yml", "--artifact-digest", DIGEST, "--release-tag", "app-v0.1.0"], text=True, capture_output=True, check=False)
        self.assertNotEqual(verified.returncode, 0)


if __name__ == "__main__":
    unittest.main()
