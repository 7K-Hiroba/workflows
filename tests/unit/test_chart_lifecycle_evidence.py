from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from scripts.lib.evidence import build, collect_lanes, verify


class ChartLifecycleEvidenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.source_sha = "a" * 40
        self.lane_name = "chart-lifecycle-example"
        self.lane = {
            "schema": "inari.lane-result.v1",
            "lane": self.lane_name,
            "status": "passed",
            "sourceSha": self.source_sha,
            "prHeadSha": "c" * 40,
            "workflowSha": "b" * 40,
            "runId": "123",
            "runAttempt": "1",
            "startedAt": "2026-11-24T00:00:00Z",
            "finishedAt": "2026-11-24T00:00:02Z",
            "chartName": "example",
            "chartPath": "charts/example",
            "releaseName": "example",
            "namespace": "default",
            "clusterName": "hiroba-chart-123",
            "clusterCreateCount": 1,
            "clusterDeleteCount": 1,
            "freshState": True,
            "cleanedUp": True,
            "fixtureOnly": False,
            "evidenceScope": "application",
            "appEvidenceEligible": True,
            "functionalE2E": False,
            "deployedReadiness": "not-tested",
            "phases": [
                {"phase": "install", "version": "0.0.9", "packageDigest": "sha256:" + "1" * 64, "status": "passed", "converged": True, "assertions": "passed", "revision": 1, "releaseName": "example", "namespace": "default", "clusterName": "hiroba-chart-123", "durationSeconds": 1},
                {"phase": "upgrade", "version": "0.1.0", "packageDigest": "sha256:" + "2" * 64, "status": "passed", "converged": True, "assertions": "passed", "revision": 2, "releaseName": "example", "namespace": "default", "clusterName": "hiroba-chart-123", "durationSeconds": 1},
            ],
            "totalDurationSeconds": 2,
        }

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def write_lane(self) -> None:
        (self.root / f"{self.lane_name}.json").write_text(json.dumps(self.lane))

    def collect(self):
        self.write_lane()
        return collect_lanes(self.root, {self.lane_name}, self.source_sha)

    def build_args(self) -> SimpleNamespace:
        return SimpleNamespace(
            source_sha=self.source_sha,
            workflow_sha="b" * 40,
            artifact_digest="sha256:" + "3" * 64,
            workflow_path=".github/workflows/release-chart.yml",
            required_lane=[self.lane_name],
            app="example",
            component="example",
            trust_tier="reviewed",
            source_repository="7K-Hiroba/example",
            artifact_repository="ghcr.io/7k-hiroba/example/charts/example",
            media_type="application/vnd.cncf.helm.chart.v1",
            release_tag="example-v0.1.0",
            run_id="123",
            run_attempt="1",
        )

    def valid_predicate(self) -> dict:
        self.write_lane()
        return build(self.root, self.build_args())

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
            required_lanes={self.lane_name},
        )

    def test_valid_chart_lifecycle_builds_and_verifies(self) -> None:
        lanes = self.collect()
        self.assertEqual(lanes[0]["lane"], self.lane_name)
        self.verify_predicate(self.valid_predicate())

    def test_rejects_reversed_lane_timestamps(self) -> None:
        self.lane["finishedAt"] = "2026-11-23T23:59:59Z"
        with self.assertRaisesRegex(ValueError, "finishedAt.*startedAt"):
            self.collect()

    def test_requires_distinct_versions_and_package_digests(self) -> None:
        original = json.loads(json.dumps(self.lane))
        for field in ("version", "packageDigest"):
            with self.subTest(field=field):
                self.lane = json.loads(json.dumps(original))
                self.lane["phases"][1][field] = self.lane["phases"][0][field]
                with self.assertRaisesRegex(ValueError, "distinct"):
                    self.collect()

    def test_requires_one_fresh_cleaned_cluster_and_ordered_complete_phases(self) -> None:
        mutations = (
            ("clusterCreateCount", 2, "cluster"),
            ("clusterDeleteCount", 0, "cluster"),
            ("freshState", False, "fresh"),
            ("cleanedUp", False, "cleaned"),
        )
        original = json.loads(json.dumps(self.lane))
        for field, value, message in mutations:
            with self.subTest(field=field):
                self.lane = json.loads(json.dumps(original))
                self.lane[field] = value
                with self.assertRaisesRegex(ValueError, message):
                    self.collect()
        for phases in (self.lane["phases"][:1], list(reversed(self.lane["phases"]))):
            with self.subTest(phases=[phase["phase"] for phase in phases]):
                self.lane = json.loads(json.dumps(original))
                self.lane["phases"] = phases
                with self.assertRaisesRegex(ValueError, "ordered install.*upgrade"):
                    self.collect()

    def test_rejects_false_convergence_assertions_identity_and_readiness_claims(self) -> None:
        original = json.loads(json.dumps(self.lane))
        cases = (
            (("phases", 1, "converged"), False, "converged"),
            (("phases", 1, "assertions"), "failed", "assertions"),
            (("phases", 1, "status"), "not-run", "passed"),
            (("phases", 1, "revision"), 3, "revision"),
            (("phases", 1, "releaseName"), "other", "release"),
            (("phases", 1, "namespace"), "other", "namespace"),
            (("phases", 1, "clusterName"), "other", "cluster"),
            ("functionalE2E", True, "functional"),
            ("deployedReadiness", "tested", "deployed"),
            ("fixtureOnly", True, "fixture"),
            ("evidenceScope", "fixture", "application"),
            ("appEvidenceEligible", False, "eligible"),
        )
        for path, value, message in cases:
            with self.subTest(path=path):
                self.lane = json.loads(json.dumps(original))
                if isinstance(path, tuple):
                    self.lane[path[0]][path[1]][path[2]] = value
                else:
                    self.lane[path] = value
                with self.assertRaisesRegex(ValueError, message):
                    self.collect()

    def test_build_and_verifier_require_exact_lifecycle_producer_binding(self) -> None:
        original = json.loads(json.dumps(self.lane))
        for field, value in (("workflowSha", "d" * 40), ("runId", "999"), ("runAttempt", "2")):
            with self.subTest(operation="build", field=field):
                self.lane = json.loads(json.dumps(original))
                self.lane[field] = value
                self.write_lane()
                with self.assertRaisesRegex(ValueError, field):
                    build(self.root, self.build_args())
            with self.subTest(operation="verify", field=field):
                self.lane = json.loads(json.dumps(original))
                predicate = self.valid_predicate()
                lane = next(item for item in predicate["lanes"] if item["lane"] == self.lane_name)
                lane[field] = value
                predicate["evidenceDigest"] = hashlib.sha256(json.dumps(predicate["lanes"], sort_keys=True, separators=(",", ":")).encode()).hexdigest()
                with self.assertRaisesRegex(ValueError, field):
                    self.verify_predicate(predicate)

    def test_failed_lifecycle_cannot_authorize_even_with_detailed_phases(self) -> None:
        self.lane["status"] = "failed"
        with self.assertRaisesRegex(ValueError, "did not pass"):
            self.collect()


if __name__ == "__main__":
    unittest.main()
