from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.lib.evidence import collect_lanes


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


if __name__ == "__main__":
    unittest.main()
