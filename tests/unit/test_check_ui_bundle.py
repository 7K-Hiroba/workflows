from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "check-ui-bundle.py"


class UiBundleTests(unittest.TestCase):
    def run_checker(self, dist: Path, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(["python3", str(SCRIPT), "--dist", str(dist), *args], text=True, capture_output=True, check=False)

    def test_writes_deterministic_manifest_for_entry_and_chunks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dist = Path(tmp)
            (dist / "remoteEntry.js").write_text("entry\n")
            (dist / "123.async.js").write_text("chunk\n")
            (dist / "123.async.js.LICENSE.txt").write_text("license\n")
            manifest = dist / "manifest.json"
            result = self.run_checker(dist, "--output", str(manifest))
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            data = json.loads(manifest.read_text())
            self.assertEqual([entry["name"] for entry in data["files"]], ["123.async.js", "123.async.js.LICENSE.txt", "remoteEntry.js"])
            entry = next(item for item in data["files"] if item["name"] == "remoteEntry.js")
            self.assertEqual(len(entry["sha256"]), 64)

    def test_requires_remote_entry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = self.run_checker(Path(tmp))
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("remoteEntry.js", result.stdout + result.stderr)

    def test_rejects_nested_or_unsafe_assets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dist = Path(tmp)
            (dist / "remoteEntry.js").write_text("entry")
            (dist / "nested").mkdir()
            (dist / "nested/chunk.js").write_text("chunk")
            result = self.run_checker(dist)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("flat", result.stdout + result.stderr)

    def test_oci_directory_must_match_manifest_exactly(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            dist = root / "dist"
            oci = root / "oci"
            dist.mkdir()
            (dist / "remoteEntry.js").write_text("entry")
            (dist / "chunk.js").write_text("chunk")
            manifest = root / "manifest.json"
            self.assertEqual(self.run_checker(dist, "--output", str(manifest)).returncode, 0)
            oci.mkdir()
            (oci / "remoteEntry.js").write_text("entry")
            missing = self.run_checker(dist, "--oci-dir", str(oci), "--manifest", str(manifest))
            self.assertNotEqual(missing.returncode, 0)
            self.assertIn("chunk.js", missing.stdout + missing.stderr)
            (oci / "chunk.js").write_text("tampered")
            tampered = self.run_checker(dist, "--oci-dir", str(oci), "--manifest", str(manifest))
            self.assertNotEqual(tampered.returncode, 0)
            self.assertIn("checksum", (tampered.stdout + tampered.stderr).lower())
            (oci / "chunk.js").write_text("chunk")
            self.assertEqual(self.run_checker(dist, "--oci-dir", str(oci), "--manifest", str(manifest)).returncode, 0)


if __name__ == "__main__":
    unittest.main()
