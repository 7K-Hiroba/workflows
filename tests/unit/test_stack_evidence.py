from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from scripts.lib.evidence import build, collect_lanes, verify


class StackEvidenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.source_sha = "a" * 40
        self.lane = {
            "schema": "inari.lane-result.v1",
            "lane": "stack-lifecycle",
            "status": "passed",
            "sourceSha": self.source_sha,
            "workflowSha": "b" * 40,
            "runId": "123",
            "runAttempt": "1",
            "startedAt": "2026-11-23T00:00:00Z",
            "finishedAt": "2026-11-23T00:00:02Z",
            "cache": {"cacheKey": "c" * 64, "cacheHit": False},
            "clusterCreateCount": 1,
            "clusterDeleteCount": 1,
            "freshState": True,
            "cleanedUp": True,
            "functionalE2E": False,
            "deployedReadiness": "not-tested",
            "fixtureOnly": False,
            "phases": [
                {"phase": "install", "contentDigest": "sha256:" + "1" * 64, "converged": True, "durationSeconds": 1},
                {"phase": "upgrade", "contentDigest": "sha256:" + "2" * 64, "converged": True, "convergedRevision": "current", "durationSeconds": 1},
            ],
            "totalDurationSeconds": 2,
        }

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def collect(self):
        (self.root / "stack-lifecycle.json").write_text(json.dumps(self.lane))
        return collect_lanes(self.root, {"stack-lifecycle"}, self.source_sha)

    def test_valid_stack_evidence_passes(self) -> None:
        lanes = self.collect()
        self.assertEqual(lanes[0]["lane"], "stack-lifecycle")
        self.assertTrue(lanes[0]["required"])

    def test_requires_install_and_upgrade_with_distinct_content(self) -> None:
        self.lane["phases"][1]["contentDigest"] = self.lane["phases"][0]["contentDigest"]
        with self.assertRaisesRegex(ValueError, "distinct"):
            self.collect()

    def test_requires_exactly_one_fresh_cleaned_cluster(self) -> None:
        self.lane["clusterCreateCount"] = 2
        with self.assertRaisesRegex(ValueError, "cluster"):
            self.collect()

    def test_rejects_functional_or_deployed_claim(self) -> None:
        self.lane["functionalE2E"] = True
        with self.assertRaisesRegex(ValueError, "functional"):
            self.collect()

    def test_requires_both_phase_results(self) -> None:
        self.lane["phases"] = self.lane["phases"][:1]
        with self.assertRaisesRegex(ValueError, "install.*upgrade|upgrade.*install"):
            self.collect()

    def build_args(self, tier: str) -> SimpleNamespace:
        return SimpleNamespace(
            source_sha=self.source_sha,
            workflow_sha="b" * 40,
            artifact_digest="sha256:" + "3" * 64,
            workflow_path=".github/workflows/release-chart.yml",
            required_lane=["stack-lifecycle"],
            app="example",
            component="example",
            trust_tier=tier,
            source_repository="7K-Hiroba/example",
            artifact_repository="ghcr.io/7k-hiroba/example/charts/example",
            media_type="application/vnd.cncf.helm.chart.v1",
            release_tag="example-v0.1.0",
            run_id="123",
            run_attempt="1",
        )

    def valid_predicate(self) -> dict:
        (self.root / "stack-lifecycle.json").write_text(json.dumps(self.lane))
        return build(self.root, self.build_args("experimental"))

    def verify_predicate(self, predicate: dict) -> None:
        verify(
            predicate,
            source_repository="7K-Hiroba/example",
            source_sha=self.source_sha,
            workflow_repository="7K-Hiroba/workflows",
            workflow_path=".github/workflows/release-chart.yml",
            workflow_sha="b" * 40,
            artifact_repository="ghcr.io/7k-hiroba/example/charts/example",
            artifact_digest="sha256:" + "3" * 64,
            media_type="application/vnd.cncf.helm.chart.v1",
            release_tag="example-v0.1.0",
            required_lanes={"stack-lifecycle"},
        )

    def test_valid_stack_evidence_builds_and_verifies_bound_producer(self) -> None:
        self.verify_predicate(self.valid_predicate())

    def test_build_rejects_stack_producer_identity_mismatch(self) -> None:
        original = self.lane.copy()
        for field, value in (("workflowSha", "d" * 40), ("runId", "999"), ("runAttempt", "2")):
            with self.subTest(field=field):
                self.lane = original.copy()
                self.lane[field] = value
                (self.root / "stack-lifecycle.json").write_text(json.dumps(self.lane))
                with self.assertRaisesRegex(ValueError, field):
                    build(self.root, self.build_args("experimental"))

    def test_verifier_rejects_stack_producer_identity_mismatch(self) -> None:
        for field, value in (("workflowSha", "d" * 40), ("runId", "999"), ("runAttempt", "2")):
            with self.subTest(field=field):
                predicate = self.valid_predicate()
                lane = next(item for item in predicate["lanes"] if item["lane"] == "stack-lifecycle")
                lane[field] = value
                predicate["evidenceDigest"] = hashlib.sha256(json.dumps(predicate["lanes"], sort_keys=True, separators=(",", ":")).encode()).hexdigest()
                with self.assertRaisesRegex(ValueError, field):
                    self.verify_predicate(predicate)

    def test_fixture_only_stack_cannot_authorize_reviewed_application(self) -> None:
        self.lane["fixtureOnly"] = True
        (self.root / "stack-lifecycle.json").write_text(json.dumps(self.lane))
        with self.assertRaisesRegex(ValueError, "fixtureOnly"):
            build(self.root, self.build_args("reviewed"))

    def test_fixture_only_stack_remains_valid_for_experimental_fixture(self) -> None:
        self.lane["fixtureOnly"] = True
        (self.root / "stack-lifecycle.json").write_text(json.dumps(self.lane))
        predicate = build(self.root, self.build_args("experimental"))
        self.assertEqual(predicate["trustTier"], "experimental")


if __name__ == "__main__":
    unittest.main()
