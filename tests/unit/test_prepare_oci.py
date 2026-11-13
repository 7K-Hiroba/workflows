from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from tests.unit.test_validate_repository import make_valid_repo

ROOT = Path(__file__).resolve().parents[2]
PYTHON = ROOT / ".venv/bin/python"
SHA = "a" * 40


class PrepareOciTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        make_valid_repo(self.root)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def run_prepare(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run([str(PYTHON), str(ROOT / "scripts/prepare-oci-artifacts.py"), "--root", str(self.root), "--source-sha", SHA, *args], text=True, capture_output=True, check=False)

    def test_package_and_template_descriptors(self) -> None:
        package = self.run_prepare("--kind", "package", "--name", "app")
        self.assertEqual(package.returncode, 0, package.stdout + package.stderr)
        descriptor = json.loads(package.stdout)[0]
        self.assertEqual(descriptor["repository"], "ghcr.io/7k-hiroba/workflows-scaffold/catalog/app")
        self.assertEqual(descriptor["releaseTag"], "app-v0.1.0")
        self.assertEqual(descriptor["channel"], "incubating")
        template = self.run_prepare("--kind", "template", "--name", "service")
        self.assertEqual(template.returncode, 0, template.stdout + template.stderr)
        self.assertEqual(json.loads(template.stdout)[0]["mediaType"], "application/vnd.inari.template.v1")

    def test_indexes_require_evidence_and_use_source_sha(self) -> None:
        missing = self.run_prepare("--kind", "indexes")
        self.assertNotEqual(missing.returncode, 0)
        evidence = self.root / "evidence.json"
        artifacts = {}
        for kind, name in (("catalog", "admission-example"), ("catalog", "app"), ("catalog", "observability-pack"), ("template", "service")):
            artifacts[f"{kind}/{name}"] = {
                "digest": "sha256:" + (name.encode().hex().ljust(64, "0")[:64]),
                "mediaType": "application/vnd.inari.template.v1" if kind == "template" else "application/vnd.inari.catalog.package.v1+yaml",
                "sourceSha": SHA,
                "signature": {"verified": True},
                "provenance": {"verified": True},
                "testEvidence": {"status": "passed"},
            }
        evidence.write_text(json.dumps({"sourceSha": SHA, "artifacts": artifacts}))
        result = self.run_prepare("--kind", "indexes", "--evidence", str(evidence))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        descriptors = json.loads(result.stdout)
        self.assertEqual(len(descriptors), 2)
        self.assertTrue(all(item["tag"] == SHA for item in descriptors))
        self.assertTrue(all(item["channel"] == "latest" for item in descriptors))
        self.assertTrue((self.root / "catalog.yaml").is_file())


if __name__ == "__main__":
    unittest.main()
