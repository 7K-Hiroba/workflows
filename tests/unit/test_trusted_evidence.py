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
        (self.evidence / "validate.json").write_text(json.dumps({"schema": "inari.lane-result.v1", "lane": "validate", "status": "passed", "sourceSha": SOURCE}))
        (self.evidence / "runtime.json").write_text(json.dumps({"schema": "inari.lane-result.v1", "lane": "runtime", "status": "passed", "sourceSha": SOURCE}))
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
        verified = self.verify_output()
        self.assertEqual(verified.returncode, 0, verified.stdout + verified.stderr)

    def test_rejects_failed_or_missing_required_lane(self) -> None:
        (self.evidence / "runtime.json").write_text(json.dumps({"schema": "inari.lane-result.v1", "lane": "runtime", "status": "failed", "sourceSha": SOURCE}))
        self.assertNotEqual(self.run_build().returncode, 0)
        (self.evidence / "runtime.json").write_text(json.dumps({"schema": "inari.lane-result.v1", "lane": "runtime", "status": "passed", "sourceSha": SOURCE}))
        (self.evidence / "validate.json").unlink()
        self.assertNotEqual(self.run_build().returncode, 0)

    def test_rejects_stale_or_unrelated_compat(self) -> None:
        stale = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat().replace("+00:00", "Z")
        (self.evidence / "compat-report.json").write_text(json.dumps({"schema": "inari.compat-report.v1", "status": "passed", "sourceSha": SOURCE, "completedAt": stale, "entries": [{"status": "passed"}]}))
        self.assertNotEqual(self.run_build().returncode, 0)
        (self.evidence / "compat-report.json").write_text(json.dumps({"schema": "inari.compat-report.v1", "status": "passed", "sourceSha": "d" * 40, "completedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"), "entries": [{"status": "passed"}]}))
        self.assertNotEqual(self.run_build().returncode, 0)

    def verify_output(self, *extra: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run([
            "python3", str(VERIFY), "--predicate", str(self.output),
            "--source-repository", "7K-Hiroba/workflows-scaffold", "--source-sha", SOURCE,
            "--workflow-path", ".github/workflows/release-oci.yml", "--workflow-sha", WORKFLOW,
            "--artifact-repository", "ghcr.io/7k-hiroba/workflows-scaffold/catalog/app",
            "--artifact-digest", DIGEST, "--media-type", "application/vnd.inari.catalog.package.v1+yaml",
            "--release-tag", "app-v0.1.0", "--required-lane", "validate", "--required-lane", "runtime", *extra,
        ], text=True, capture_output=True, check=False)

    def test_verifier_enforces_all_release_bindings_and_required_lanes(self) -> None:
        self.assertEqual(self.run_build().returncode, 0)
        verified = self.verify_output()
        self.assertEqual(verified.returncode, 0, verified.stdout + verified.stderr)
        for args in (
            ("--workflow-sha", "e" * 40),
            ("--artifact-repository", "ghcr.io/7k-hiroba/other/catalog/app"),
            ("--media-type", "application/vnd.inari.template.v1"),
        ):
            with self.subTest(args=args):
                # Replace the default duplicate argument with the mismatched expectation.
                result = self.verify_output(*args)
                self.assertNotEqual(result.returncode, 0)

    def test_verifier_rejects_missing_required_lane_and_stale_completion(self) -> None:
        self.assertEqual(self.run_build().returncode, 0)
        predicate = json.loads(self.output.read_text())
        predicate["lanes"] = [lane for lane in predicate["lanes"] if lane["lane"] != "runtime"]
        self.output.write_text(json.dumps(predicate))
        self.assertNotEqual(self.verify_output().returncode, 0)
        self.assertEqual(self.run_build().returncode, 0)
        predicate = json.loads(self.output.read_text())
        predicate["finishedAt"] = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat().replace("+00:00", "Z")
        self.output.write_text(json.dumps(predicate))
        self.assertNotEqual(self.verify_output().returncode, 0)

    def test_rejects_unexpected_producer_and_mismatched_verification(self) -> None:
        result = self.run_build("--workflow-path", ".github/workflows/untrusted.yml")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.run_build().returncode, 0)
        verified = self.verify_output("--source-sha", "d" * 40)
        self.assertNotEqual(verified.returncode, 0)

    def test_rejects_wrong_or_missing_generic_lane_source(self) -> None:
        path = self.evidence / "validate.json"
        path.write_text(json.dumps({"schema": "inari.lane-result.v1", "lane": "validate", "status": "passed", "sourceSha": "d" * 40}))
        self.assertNotEqual(self.run_build().returncode, 0)
        path.write_text(json.dumps({"schema": "inari.lane-result.v1", "lane": "validate", "status": "passed"}))
        self.assertNotEqual(self.run_build().returncode, 0)

    def test_verifier_rejects_generic_lane_source_conflict(self) -> None:
        self.assertEqual(self.run_build().returncode, 0)
        predicate = json.loads(self.output.read_text())
        validate = next(lane for lane in predicate["lanes"] if lane["lane"] == "validate")
        validate["sourceSha"] = "d" * 40
        import hashlib
        predicate["evidenceDigest"] = hashlib.sha256(json.dumps(predicate["lanes"], sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        self.output.write_text(json.dumps(predicate))
        self.assertNotEqual(self.verify_output().returncode, 0)

    def write_fixture_lane(self) -> None:
        (self.evidence / "runtime-smoke.json").write_text(json.dumps({
            "schema": "inari.lane-result.v1", "lane": "runtime-smoke", "status": "passed", "sourceSha": SOURCE,
            "targetAdapter": "manifests", "targetComponent": "", "targetVersion": "0.1.0",
            "fixtureOnly": True, "executableProfiles": ["ci"], "evidenceScope": "fixture", "appEvidenceEligible": False,
        }))

    def run_fixture_build(self, trust_tier: str = "experimental", app_artifact: bool = False) -> subprocess.CompletedProcess[str]:
        self.write_fixture_lane()
        workflow = ".github/workflows/release-oci.yml" if app_artifact else ".github/workflows/release-smoke-suite.yml"
        repository = "ghcr.io/7k-hiroba/workflows-scaffold/catalog/app" if app_artifact else "ghcr.io/7k-hiroba/workflows-scaffold/smoke/workflows-scaffold-smoke"
        media_type = "application/vnd.inari.catalog.package.v1+yaml" if app_artifact else "application/vnd.inari.smoke.suite.v1+yaml"
        tag = "app-v0.1.0" if app_artifact else "workflows-scaffold-smoke-v0.1.0"
        return subprocess.run([
            "python3", str(SCRIPT), "--evidence-dir", str(self.evidence), "--output", str(self.output),
            "--app", "workflows-scaffold", "--component", "app", "--trust-tier", trust_tier,
            "--source-repository", "7K-Hiroba/workflows-scaffold", "--source-sha", SOURCE, "--workflow-sha", WORKFLOW,
            "--workflow-path", workflow, "--run-id", "123", "--run-attempt", "1",
            "--artifact-repository", repository, "--artifact-digest", DIGEST,
            "--media-type", media_type, "--release-tag", tag,
            "--required-lane", "validate", "--required-lane", "runtime-smoke",
        ], text=True, capture_output=True, check=False)

    def verify_fixture(self, app_artifact: bool = False) -> subprocess.CompletedProcess[str]:
        workflow = ".github/workflows/release-oci.yml" if app_artifact else ".github/workflows/release-smoke-suite.yml"
        repository = "ghcr.io/7k-hiroba/workflows-scaffold/catalog/app" if app_artifact else "ghcr.io/7k-hiroba/workflows-scaffold/smoke/workflows-scaffold-smoke"
        media_type = "application/vnd.inari.catalog.package.v1+yaml" if app_artifact else "application/vnd.inari.smoke.suite.v1+yaml"
        tag = "app-v0.1.0" if app_artifact else "workflows-scaffold-smoke-v0.1.0"
        return subprocess.run([
            "python3", str(VERIFY), "--predicate", str(self.output),
            "--source-repository", "7K-Hiroba/workflows-scaffold", "--source-sha", SOURCE,
            "--workflow-path", workflow, "--workflow-sha", WORKFLOW,
            "--artifact-repository", repository, "--artifact-digest", DIGEST, "--media-type", media_type,
            "--release-tag", tag, "--required-lane", "validate", "--required-lane", "runtime-smoke",
        ], text=True, capture_output=True, check=False)

    def chartless_artifact_args(self, kind: str) -> list[str]:
        app = "hiroba-chartless-smoke"
        if kind == "template":
            component = f"templates-{app}"
            workflow = ".github/workflows/release-oci.yml"
            repository = f"ghcr.io/7k-hiroba/{app}/templates/{app}"
            media_type = "application/vnd.inari.template.v1"
            tag = f"{app}-v0.1.0"
        else:
            component = f"{app}-smoke"
            workflow = ".github/workflows/release-smoke-suite.yml"
            repository = f"ghcr.io/7k-hiroba/{app}/smoke/{app}-smoke"
            media_type = "application/vnd.inari.smoke.suite.v1+yaml"
            tag = f"{app}-smoke-v0.1.0"
        return [
            "--app", app, "--component", component, "--trust-tier", "experimental",
            "--source-repository", "7K-Hiroba/workflows", "--source-sha", SOURCE, "--workflow-sha", WORKFLOW,
            "--workflow-path", workflow, "--run-id", "123", "--run-attempt", "1",
            "--artifact-repository", repository, "--artifact-digest", DIGEST,
            "--media-type", media_type, "--release-tag", tag,
            "--required-lane", "validate", "--required-lane", "runtime-smoke",
        ]

    def run_chartless_build(self, kind: str, include_eligibility: bool = True) -> subprocess.CompletedProcess[str]:
        self.write_fixture_lane()
        if not include_eligibility:
            path = self.evidence / "runtime-smoke.json"
            lane = json.loads(path.read_text())
            del lane["appEvidenceEligible"]
            path.write_text(json.dumps(lane))
        return subprocess.run([
            "python3", str(SCRIPT), "--evidence-dir", str(self.evidence), "--output", str(self.output),
            *self.chartless_artifact_args(kind),
        ], text=True, capture_output=True, check=False)

    def verify_chartless(self, kind: str) -> subprocess.CompletedProcess[str]:
        supported = {
            "--source-repository", "--source-sha", "--workflow-path", "--workflow-sha",
            "--artifact-repository", "--artifact-digest", "--media-type", "--release-tag", "--required-lane",
        }
        args = self.chartless_artifact_args(kind)
        verify_args = [value for index in range(0, len(args), 2) if args[index] in supported for value in args[index:index + 2]]
        return subprocess.run([
            "python3", str(VERIFY), "--predicate", str(self.output), *verify_args,
        ], text=True, capture_output=True, check=False)

    def test_chartless_template_and_smoke_predicates_are_admitted_as_fixture_only(self) -> None:
        for kind in ("template", "smoke"):
            with self.subTest(kind=kind):
                result = self.run_chartless_build(kind)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                predicate = json.loads(self.output.read_text())
                runtime = next(lane for lane in predicate["lanes"] if lane["lane"] == "runtime-smoke")
                self.assertTrue(runtime["fixtureOnly"])
                self.assertEqual(runtime["targetAdapter"], "manifests")
                self.assertEqual(runtime["executableProfiles"], ["ci"])
                self.assertEqual(runtime["evidenceScope"], "fixture")
                self.assertFalse(runtime["appEvidenceEligible"])
                self.assertFalse(predicate["appEvidenceEligible"])
                verified = self.verify_chartless(kind)
                self.assertEqual(verified.returncode, 0, verified.stdout + verified.stderr)

    def test_chartless_predicates_reject_missing_eligibility_fail_closed(self) -> None:
        for kind in ("template", "smoke"):
            with self.subTest(kind=kind):
                result = self.run_chartless_build(kind, include_eligibility=False)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("missing fixture eligibility metadata", result.stdout + result.stderr)

    def test_fixture_only_evidence_is_signed_as_ci_only_and_ineligible(self) -> None:
        result = self.run_fixture_build()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        predicate = json.loads(self.output.read_text())
        self.assertEqual(predicate["evidenceScope"], "fixture")
        self.assertFalse(predicate["appEvidenceEligible"])
        self.assertEqual(predicate["executableProfiles"], ["ci"])
        verified = self.verify_fixture()
        self.assertEqual(verified.returncode, 0, verified.stdout + verified.stderr)

    def test_fixture_only_cannot_authorize_reviewed_application_evidence(self) -> None:
        result = self.run_fixture_build(trust_tier="reviewed", app_artifact=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("fixture", (result.stdout + result.stderr).lower())
        self.assertEqual(self.run_fixture_build(app_artifact=True).returncode, 0)
        predicate = json.loads(self.output.read_text())
        predicate["trustTier"] = "reviewed"
        self.output.write_text(json.dumps(predicate))
        self.assertNotEqual(self.verify_fixture(app_artifact=True).returncode, 0)

    def test_fixture_only_evidence_rejects_eligibility_tampering(self) -> None:
        self.assertEqual(self.run_fixture_build().returncode, 0)
        predicate = json.loads(self.output.read_text())
        runtime = next(lane for lane in predicate["lanes"] if lane["lane"] == "runtime-smoke")
        runtime["appEvidenceEligible"] = True
        import hashlib
        predicate["evidenceDigest"] = hashlib.sha256(json.dumps(predicate["lanes"], sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        self.output.write_text(json.dumps(predicate))
        self.assertNotEqual(self.verify_fixture().returncode, 0)

    def test_second_identical_rerun_attestation_is_idempotent(self) -> None:
        self.assertEqual(self.run_build().returncode, 0)
        predicate = json.loads(self.output.read_text())
        self.output.write_text(json.dumps([{"predicate": predicate}, {"predicate": predicate}]))
        self.assertEqual(self.verify_output().returncode, 0)

    def test_chart_repair_checks_every_distinct_attempt_and_rejects_conflict(self) -> None:
        chart_args = ("--workflow-path", ".github/workflows/release-chart.yml")
        self.assertEqual(self.run_build(*chart_args).returncode, 0)
        first = json.loads(self.output.read_text())
        second = json.loads(json.dumps(first))
        second["producer"]["runAttempt"] = "2"
        self.output.write_text(json.dumps([{"predicate": first}, {"predicate": second}]))
        self.assertEqual(self.verify_output(*chart_args).returncode, 0)
        second["sourceSha"] = "d" * 40
        self.output.write_text(json.dumps([{"predicate": first}, {"predicate": second}]))
        self.assertNotEqual(self.verify_output(*chart_args).returncode, 0)

    def test_late_repair_requires_fresh_valid_predicate_and_bound_history(self) -> None:
        self.assertEqual(self.run_build().returncode, 0)
        fresh = json.loads(self.output.read_text())
        fresh["producer"]["runAttempt"] = "2"
        stale = json.loads(json.dumps(fresh))
        stale["producer"]["runAttempt"] = "1"
        stale["finishedAt"] = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat().replace("+00:00", "Z")
        self.output.write_text(json.dumps([{"predicate": stale}, {"predicate": fresh}]))
        self.assertEqual(self.verify_output().returncode, 0)
        self.output.write_text(json.dumps([{"predicate": stale}]))
        self.assertNotEqual(self.verify_output().returncode, 0)
        future = json.loads(json.dumps(fresh))
        future["finishedAt"] = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat().replace("+00:00", "Z")
        self.output.write_text(json.dumps([{"predicate": fresh}, {"predicate": future}]))
        self.assertNotEqual(self.verify_output().returncode, 0)
        stale["sourceSha"] = "d" * 40
        self.output.write_text(json.dumps([{"predicate": stale}, {"predicate": fresh}]))
        self.assertNotEqual(self.verify_output().returncode, 0)


if __name__ == "__main__":
    unittest.main()
