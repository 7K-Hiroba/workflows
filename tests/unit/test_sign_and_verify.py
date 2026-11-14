from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = "a" * 40
WORKFLOW = "b" * 40
DIGEST = "sha256:" + "c" * 64
REPO = "ghcr.io/7k-hiroba/workflows-scaffold/catalog/app"
REF = REPO + "@" + DIGEST


class SignAndVerifyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.log = self.root / "calls.log"
        cosign = self.bin / "cosign"
        cosign.write_text("#!/usr/bin/env bash\necho cosign \"$@\" >> \"$CALL_LOG\"\nif [[ \"$1\" == verify-attestation ]]; then cat \"$PREDICATE_DOC\"; fi\n")
        gh = self.bin / "gh"
        gh.write_text("#!/usr/bin/env bash\necho gh \"$@\" >> \"$CALL_LOG\"\necho '{\"predicateType\":\"https://slsa.dev/provenance/v1\"}'\n")
        cosign.chmod(0o755)
        gh.chmod(0o755)
        self.evidence = self.root / "evidence"
        self.evidence.mkdir()
        (self.evidence / "validate.json").write_text(json.dumps({"schema": "inari.lane-result.v1", "lane": "validate", "status": "passed"}))
        self.predicate_doc = self.root / "predicate.json"
        self.env = {
            **os.environ,
            "PATH": str(self.bin) + ":" + os.environ["PATH"],
            "CALL_LOG": str(self.log),
            "PREDICATE_DOC": str(self.predicate_doc),
            "ARTIFACT_REF": REF,
            "ARTIFACT_REPOSITORY": REPO,
            "ARTIFACT_DIGEST": DIGEST,
            "MEDIA_TYPE": "application/vnd.inari.catalog.package.v1+yaml",
            "APP": "workflows-scaffold",
            "COMPONENT": "app",
            "TRUST_TIER": "reviewed",
            "SOURCE_REPOSITORY": "7K-Hiroba/workflows-scaffold",
            "SOURCE_SHA": SOURCE,
            "WORKFLOW_SHA": WORKFLOW,
            "WORKFLOW_PATH": ".github/workflows/release-oci.yml",
            "RUN_ID": "123",
            "RUN_ATTEMPT": "1",
            "RELEASE_TAG": "app-v0.1.0",
            "EVIDENCE_DIR": str(self.evidence),
            "REQUIRED_LANES": "validate",
            "PREDICATE_OUT": str(self.root / "built.json"),
            "VERIFICATION_RECEIPT": str(self.root / "receipt.json"),
        }

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_signs_and_attests_only_after_valid_evidence(self) -> None:
        result = subprocess.run(["bash", str(ROOT / "scripts/sign-and-attest.sh")], env=self.env, text=True, capture_output=True, check=False)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        calls = self.log.read_text().splitlines()
        self.assertIn(f"cosign sign --yes {REF}", calls[0])
        self.assertIn("cosign attest --yes", calls[1])
        self.assertIn("--type https://inari.dev/attestations/test-evidence/v1", calls[1])
        predicate = json.loads((self.root / "built.json").read_text())
        self.assertEqual(predicate["artifact"]["digest"], DIGEST)

    def test_invalid_evidence_stops_before_cosign(self) -> None:
        (self.evidence / "validate.json").write_text(json.dumps({"schema": "inari.lane-result.v1", "lane": "validate", "status": "failed"}))
        result = subprocess.run(["bash", str(ROOT / "scripts/sign-and-attest.sh")], env=self.env, text=True, capture_output=True, check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.log.exists())

    def test_verify_requires_signature_slsa_and_matching_predicate(self) -> None:
        self.assertEqual(subprocess.run(["bash", str(ROOT / "scripts/sign-and-attest.sh")], env=self.env, text=True, capture_output=True, check=False).returncode, 0)
        self.predicate_doc.write_text((self.root / "built.json").read_text())
        verify_env = {**self.env, "EXPECTED_PUBLISHER": "https://github.com/7K-Hiroba/workflows/.github/workflows/release-oci.yml@"}
        result = subprocess.run(["bash", str(ROOT / "scripts/verify-release.sh")], env=verify_env, text=True, capture_output=True, check=False)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.predicate_doc.write_text(json.dumps({"schema": "inari.test-evidence.v1", "sourceSha": "d" * 40, "producer": {"workflowPath": ".github/workflows/release-oci.yml"}, "artifact": {"digest": DIGEST}, "releaseTag": "app-v0.1.0", "lanes": [{"lane": "validate", "status": "passed"}]}))
        result = subprocess.run(["bash", str(ROOT / "scripts/verify-release.sh")], env=verify_env, text=True, capture_output=True, check=False)
        self.assertNotEqual(result.returncode, 0)

    def test_mark_verified_requires_matching_receipt(self) -> None:
        self.assertEqual(subprocess.run(["bash", str(ROOT / "scripts/sign-and-attest.sh")], env=self.env, text=True, capture_output=True, check=False).returncode, 0)
        self.predicate_doc.write_text((self.root / "built.json").read_text())
        verify_env = {**self.env, "EXPECTED_PUBLISHER": "https://github.com/7K-Hiroba/workflows/.github/workflows/release-oci.yml@"}
        self.assertEqual(subprocess.run(["bash", str(ROOT / "scripts/verify-release.sh")], env=verify_env, text=True, capture_output=True, check=False).returncode, 0)
        artifact = self.root / "artifact.json"
        artifact.write_text(json.dumps({"repository": REPO, "digest": DIGEST, "mediaType": "application/vnd.inari.catalog.package.v1+yaml", "sourceSha": SOURCE, "signature": {"verified": False}, "provenance": {"verified": False}, "testEvidence": {"status": "pending"}}))
        result = subprocess.run(["python3", str(ROOT / "scripts/mark-artifact-verified.py"), "--artifact", str(artifact), "--receipt", str(self.root / "receipt.json"), "--predicate", str(self.root / "built.json")], text=True, capture_output=True, check=False)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        marked = json.loads(artifact.read_text())
        self.assertTrue(marked["signature"]["verified"])
        self.assertTrue(marked["provenance"]["verified"])
        self.assertEqual(marked["testEvidence"]["status"], "passed")
        artifact.write_text(json.dumps({"repository": REPO, "digest": DIGEST, "sourceSha": "d" * 40, "signature": {"verified": False}, "provenance": {"verified": False}, "testEvidence": {"status": "pending"}}))
        result = subprocess.run(["python3", str(ROOT / "scripts/mark-artifact-verified.py"), "--artifact", str(artifact), "--receipt", str(self.root / "receipt.json"), "--predicate", str(self.root / "built.json")], text=True, capture_output=True, check=False)
        self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
