from __future__ import annotations

import io
import json
import os
import subprocess
import tarfile
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/release-backend.sh"
DIGEST = "sha256:" + "c" * 64
OTHER = "sha256:" + "d" * 64


class BackendReleaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.context = self.root / "context"
        self.context.mkdir()
        self.candidate = self.root / "candidate.tar"
        index = json.dumps({"schemaVersion": 2, "manifests": [{"mediaType": "application/vnd.oci.image.manifest.v1+json", "digest": DIGEST}]}).encode()
        with tarfile.open(self.candidate, "w") as archive:
            info = tarfile.TarInfo("index.json")
            info.size = len(index)
            archive.addfile(info, io.BytesIO(index))
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.log = self.root / "calls.log"
        self.state = self.root / "state"
        docker = self.bin / "docker"
        docker.write_text("#!/usr/bin/env bash\nset -e\necho docker \"$@\" >> \"$CALL_LOG\"\nout=\"\"\nwhile [[ $# -gt 0 ]]; do if [[ \"$1\" == --output ]]; then out=${2#type=oci,dest=}; shift 2; else shift; fi; done\ncp \"$CANDIDATE\" \"$out\"\n")
        crane = self.bin / "crane"
        crane.write_text("#!/usr/bin/env bash\nset -e\necho crane \"$@\" >> \"$CALL_LOG\"\ncase \"$1\" in\n  digest) if [[ -f \"$STATE\" ]]; then cat \"$STATE\"; else exit 1; fi ;;\n  push) printf '%s' \"$EXPECTED_DIGEST\" > \"$STATE\" ;;\nesac\n")
        docker.chmod(0o755)
        crane.chmod(0o755)
        self.env = {**os.environ, "PATH": str(self.bin) + ":" + os.environ["PATH"], "CALL_LOG": str(self.log), "STATE": str(self.state), "CANDIDATE": str(self.candidate), "EXPECTED_DIGEST": DIGEST}

    def tearDown(self) -> None:
        self.temp.cleanup()

    def publish(self) -> subprocess.CompletedProcess[str]:
        return subprocess.run([
            "bash", str(SCRIPT), "--context", str(self.context), "--repository", "ghcr.io/7k-hiroba/app/extension",
            "--tag", "1.0.0", "--source-sha", "a" * 40, "--output", str(self.root / "artifact.json"),
        ], env=self.env, text=True, capture_output=True, check=False)

    def test_always_builds_and_pushes_missing_candidate(self) -> None:
        result = self.publish()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        calls = self.log.read_text()
        self.assertIn("docker buildx build", calls)
        self.assertIn("crane push", calls)
        artifact = json.loads((self.root / "artifact.json").read_text())
        self.assertEqual(artifact["digest"], DIGEST)
        self.assertEqual(artifact["mediaType"], "application/vnd.oci.image.manifest.v1+json")

    def test_matching_existing_digest_is_reused_after_candidate_build(self) -> None:
        self.state.write_text(DIGEST)
        result = self.publish()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        calls = self.log.read_text()
        self.assertIn("docker buildx build", calls)
        self.assertNotIn("crane push", calls)

    def test_tampered_existing_image_fails_before_push_or_attestation(self) -> None:
        self.state.write_text(OTHER)
        result = self.publish()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("existing backend image digest differs", result.stdout + result.stderr)
        calls = self.log.read_text()
        self.assertIn("docker buildx build", calls)
        self.assertNotIn("crane push", calls)
        self.assertFalse((self.root / "artifact.json").exists())


if __name__ == "__main__":
    unittest.main()
