from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/package-and-publish.sh"
DIGEST = "sha256:" + "a" * 64


class PackagePublishTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / "source"
        self.source.mkdir()
        (self.source / "package.yaml").write_text("version: 0.1.0\n")
        (self.source / "rgd.yaml").write_text("kind: ResourceGraphDefinition\n")
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.log = self.root / "calls.log"
        self.state = self.root / "state"
        crane = self.bin / "crane"
        crane.write_text("#!/usr/bin/env bash\necho crane \"$@\" >> \"$CALL_LOG\"\nif [[ -f \"$STATE\" ]]; then cat \"$STATE\"; else exit 1; fi\n")
        oras = self.bin / "oras"
        oras.write_text("""#!/usr/bin/env bash
set -e
echo oras \"$@\" >> \"$CALL_LOG\"
case \"$1\" in
  push)
    printf '%s' \"$FAKE_DIGEST\" > \"$STATE\"
    echo \"Digest: $FAKE_DIGEST\"
    ;;
  pull)
    out=""
    while [[ $# -gt 0 ]]; do
      if [[ \"$1\" == --output ]]; then out=$2; shift 2; else shift; fi
    done
    mkdir -p \"$out\"
    cp -R \"$SOURCE_DIR\"/. \"$out\"/
    if [[ -n \"$TAMPER\" ]]; then echo tampered > \"$out/tampered\"; fi
    ;;
  *) exit 0 ;;
esac
""")
        crane.chmod(0o755)
        oras.chmod(0o755)
        self.env = {
            **os.environ,
            "PATH": str(self.bin) + ":" + os.environ["PATH"],
            "CALL_LOG": str(self.log),
            "STATE": str(self.state),
            "DIGEST": DIGEST,
            "FAKE_DIGEST": DIGEST,
            "SOURCE_DIR": str(self.source),
            "TAMPER": "",
        }

    def tearDown(self) -> None:
        self.temp.cleanup()

    def run_publish(self, *extra: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run([
            "bash", str(SCRIPT), "--source", str(self.source), "--repository", "ghcr.io/7k-hiroba/app/catalog/pkg",
            "--tag", "0.1.0", "--artifact-type", "application/vnd.inari.catalog.package.v1+yaml",
            "--source-sha", "b" * 40, "--output", str(self.root / "artifact.json"), *extra,
        ], env=self.env, text=True, capture_output=True, check=False)

    def test_new_artifact_pushes_and_records_digest_without_channel_move(self) -> None:
        result = self.run_publish("--channel", "stable")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        artifact = json.loads((self.root / "artifact.json").read_text())
        self.assertEqual(artifact["digest"], DIGEST)
        self.assertEqual(artifact["signature"]["verified"], False)
        calls = self.log.read_text()
        self.assertIn("oras push", calls)
        self.assertNotIn("oras tag", calls)

    def test_existing_identical_artifact_does_not_push(self) -> None:
        self.state.write_text(DIGEST)
        result = self.run_publish()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("oras push", self.log.read_text())

    def test_existing_different_content_fails_without_push(self) -> None:
        self.state.write_text(DIGEST)
        self.env["TAMPER"] = "yes"
        result = self.run_publish()
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("oras push", self.log.read_text())

    def test_rejects_latest(self) -> None:
        result = self.run_publish("--tag", "latest")
        self.assertNotEqual(result.returncode, 0)

    def test_index_file_uses_raw_yaml_layer(self) -> None:
        source = self.root / "index"
        source.mkdir()
        (source / "catalog.yaml").write_text("packages: []\n")
        self.env["SOURCE_DIR"] = str(source)
        result = subprocess.run([
            "bash", str(SCRIPT), "--source", str(source), "--file", "catalog.yaml", "--repository", "ghcr.io/7k-hiroba/app/catalog/index",
            "--tag", "a" * 40, "--artifact-type", "application/vnd.inari.catalog.index.v1+yaml", "--source-sha", "a" * 40,
            "--output", str(self.root / "index.json"),
        ], env=self.env, text=True, capture_output=True, check=False)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("catalog.yaml:text/yaml", self.log.read_text())


if __name__ == "__main__":
    unittest.main()
