from __future__ import annotations

import json
import os
import shutil
import subprocess
import tarfile
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONTEXT = ROOT / "scaffold/extension"


def manifest_digest(archive: Path) -> str:
    with tarfile.open(archive) as bundle:
        index = json.load(bundle.extractfile("index.json"))
    manifests = index.get("manifests", [])
    if len(manifests) != 1:
        raise AssertionError("expected exactly one image manifest")
    return manifests[0]["digest"]


def buildx_command() -> list[str] | None:
    candidate = ["docker", "buildx"]
    probe = subprocess.run([*candidate, "version"], text=True, capture_output=True, check=False)
    if probe.returncode == 0:
        return candidate
    plugin = Path.home() / ".docker/cli-plugins/docker-buildx"
    if plugin.is_file():
        probe = subprocess.run([str(plugin), "version"], text=True, capture_output=True, check=False)
        if probe.returncode == 0:
            return [str(plugin)]
    return None


@unittest.skipIf(buildx_command() is None, "docker buildx is not available")
class BackendReproducibilityIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.work = Path(self.temp.name)
        self.env = {**os.environ, "BUILDX_CONFIG": str(self.work / "buildx-config")}
        probe = subprocess.run(["docker", "info"], text=True, capture_output=True, check=False, env=self.env)
        if probe.returncode != 0:
            self.skipTest("docker daemon is not reachable")
        epoch = subprocess.run(
            ["git", "-C", str(ROOT), "log", "-1", "--format=%ct", "HEAD"],
            text=True, capture_output=True, check=False,
        )
        if epoch.returncode != 0 or not epoch.stdout.strip().isdigit():
            self.skipTest("source commit timestamp is unavailable")
        self.epoch = epoch.stdout.strip()
        self.buildx = buildx_command()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def build(self, context: Path, name: str) -> str:
        archive = self.work / f"{name}.tar"
        result = subprocess.run(
            [
                *self.buildx, "build", "--no-cache",
                "--build-arg", f"SOURCE_DATE_EPOCH={self.epoch}",
                "--output", f"type=oci,dest={archive},rewrite-timestamp=true",
                "--tag", f"hiroba-reproducibility-test:{name}",
                "--provenance=false", "--sbom=false", str(context),
            ],
            text=True, capture_output=True, check=False, env=self.env, timeout=900,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return manifest_digest(archive)

    def test_same_source_builds_are_byte_identical(self) -> None:
        first = self.build(CONTEXT, "first")
        second = self.build(CONTEXT, "second")
        self.assertEqual(first, second, "same source must produce the same backend image digest")

    def test_changed_content_produces_a_different_digest(self) -> None:
        baseline = self.build(CONTEXT, "baseline")
        modified = self.work / "context-modified"
        shutil.copytree(CONTEXT, modified)
        source = modified / "extension.go"
        content = source.read_text()
        marker = "workflows-scaffold"
        self.assertIn(marker, content)
        source.write_text(content.replace(marker, "workflows-scaffold-changed", 1))
        changed = self.build(modified, "changed")
        self.assertNotEqual(baseline, changed, "changed source must produce a different backend image digest")


if __name__ == "__main__":
    unittest.main()
