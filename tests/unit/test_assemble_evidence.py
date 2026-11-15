from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from tests.unit.test_validate_repository import make_valid_repo

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/assemble-release-evidence.py"
PREPARE = ROOT / "scripts/prepare-oci-artifacts.py"
PYTHON = ROOT / ".venv/bin/python"
SOURCE = "b" * 40
TEMPLATE_MEDIA = "application/vnd.inari.template.v1"


def verified_template_artifact() -> dict:
    return {
        "repository": "ghcr.io/7k-hiroba/workflows-scaffold/templates/service",
        "digest": "sha256:" + "a" * 64,
        "mediaType": TEMPLATE_MEDIA,
        "sourceSha": SOURCE,
        "signature": {"verified": True},
        "provenance": {"verified": True},
        "testEvidence": {"status": "passed"},
    }


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

    def test_templates_filename_assembles_verified_template_and_ready_index(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            make_valid_repo(root)
            prepared = subprocess.run([str(PYTHON), str(PREPARE), "--root", str(root), "--kind", "template", "--name", "service", "--source-sha", SOURCE], text=True, capture_output=True, check=False)
            self.assertEqual(prepared.returncode, 0, prepared.stdout + prepared.stderr)
            descriptor = json.loads(prepared.stdout)[0]
            self.assertEqual(descriptor["key"], "templates-service")
            self.assertEqual(descriptor["mediaType"], TEMPLATE_MEDIA)

            artifact = verified_template_artifact()
            artifact["repository"] = descriptor["repository"]
            artifact["mediaType"] = descriptor["mediaType"]
            artifacts = root / "artifacts"
            artifacts.mkdir()
            (artifacts / f"artifact-{descriptor['key']}.json").write_text(json.dumps(artifact))
            for name in ("admission-example", "app", "observability-pack"):
                package = subprocess.run([str(PYTHON), str(PREPARE), "--root", str(root), "--kind", "package", "--name", name, "--source-sha", SOURCE], text=True, capture_output=True, check=False)
                self.assertEqual(package.returncode, 0, package.stdout + package.stderr)
                package_descriptor = json.loads(package.stdout)[0]
                package_artifact = {
                    "repository": package_descriptor["repository"],
                    "digest": "sha256:" + name.encode().hex().ljust(64, "0")[:64],
                    "mediaType": package_descriptor["mediaType"],
                    "sourceSha": SOURCE,
                    "signature": {"verified": True},
                    "provenance": {"verified": True},
                    "testEvidence": {"status": "passed"},
                }
                (artifacts / f"artifact-{package_descriptor['key']}.json").write_text(json.dumps(package_artifact))
            output = root / "release.json"
            assembled = subprocess.run([str(PYTHON), str(SCRIPT), "--artifacts", str(artifacts), "--source-sha", SOURCE, "--output", str(output)], text=True, capture_output=True, check=False)
            self.assertEqual(assembled.returncode, 0, assembled.stdout + assembled.stderr)
            evidence = json.loads(output.read_text())
            self.assertEqual(len(evidence["artifacts"]), 4)
            self.assertEqual(evidence["artifacts"]["template/service"]["digest"], artifact["digest"])

            indexes = subprocess.run([str(PYTHON), str(PREPARE), "--root", str(root), "--kind", "indexes", "--source-sha", SOURCE, "--evidence", str(output)], text=True, capture_output=True, check=False)
            self.assertEqual(indexes.returncode, 0, indexes.stdout + indexes.stderr)
            self.assertIn("service", (root / "templates.yaml").read_text())

    def test_templates_evidence_rejects_pending_unverified_wrong_media_and_singular_alias(self) -> None:
        for mode in ("pending", "unverified", "wrong-media", "singular-alias"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                artifact = verified_template_artifact()
                filename = "artifact-templates-service.json"
                if mode == "pending":
                    artifact["testEvidence"]["status"] = "pending"
                elif mode == "unverified":
                    artifact["signature"]["verified"] = False
                elif mode == "wrong-media":
                    artifact["mediaType"] = "application/vnd.inari.catalog.package.v1+yaml"
                else:
                    filename = "artifact-template-service.json"
                (root / filename).write_text(json.dumps(artifact))
                output = root / "release.json"
                result = subprocess.run([str(PYTHON), str(SCRIPT), "--artifacts", str(root), "--source-sha", SOURCE, "--output", str(output)], text=True, capture_output=True, check=False)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
