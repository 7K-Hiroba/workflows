from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/assemble-release-evidence.py"


class AssembleEvidenceTests(unittest.TestCase):
    def test_collects_verified_artifacts_and_rejects_pending(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            artifact = {
                "repository": "ghcr.io/7k-hiroba/app/catalog/pkg",
                "digest": "sha256:" + "a" * 64,
                "mediaType": "application/vnd.inari.catalog.package.v1+yaml",
                "sourceSha": "b" * 40,
                "signature": {"verified": True},
                "provenance": {"verified": True},
                "testEvidence": {"status": "passed"},
            }
            (root / "artifact-catalog-pkg.json").write_text(json.dumps(artifact))
            output = root / "release.json"
            result = subprocess.run([str(ROOT / ".venv/bin/python"), str(SCRIPT), "--artifacts", str(root), "--source-sha", "b" * 40, "--output", str(output)], text=True, capture_output=True, check=False)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(json.loads(output.read_text())["artifacts"]["catalog/pkg"]["digest"], artifact["digest"])
            artifact["testEvidence"]["status"] = "pending"
            (root / "artifact-catalog-pkg.json").write_text(json.dumps(artifact))
            result = subprocess.run([str(ROOT / ".venv/bin/python"), str(SCRIPT), "--artifacts", str(root), "--source-sha", "b" * 40, "--output", str(output)], text=True, capture_output=True, check=False)
            self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
