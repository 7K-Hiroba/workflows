from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/render-extension-release.py"
DIGEST = "sha256:" + "a" * 64


class ExtensionReleaseTests(unittest.TestCase):
    def test_renders_exact_oci_metadata_without_mutating_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "extension.yaml"
            source.write_text("spec:\n  version: 0.1.0\n  backend: {image: ghcr.io/7k-hiroba/app/extension}\n  ui: {remoteEntryOci: ghcr.io/7k-hiroba/app/extension-ui}\n")
            backend = root / "backend.json"
            backend.write_text(json.dumps({"repository": "ghcr.io/7k-hiroba/app/extension", "digest": DIGEST}))
            ui = root / "ui.json"
            ui.write_text(json.dumps({"repository": "ghcr.io/7k-hiroba/app/extension-ui", "digest": DIGEST}))
            manifest = root / "manifest.json"
            manifest.write_text(json.dumps({"files": [{"name": "remoteEntry.js", "sha256": "b" * 64}]}))
            output = root / "extension.release.yaml"
            result = subprocess.run([str(ROOT / ".venv/bin/python"), str(SCRIPT), "--extension", str(source), "--backend", str(backend), "--ui", str(ui), "--ui-manifest", str(manifest), "--output", str(output)], text=True, capture_output=True, check=False)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            data = yaml.safe_load(output.read_text())
            self.assertEqual(data["spec"]["backend"]["image"], "ghcr.io/7k-hiroba/app/extension@" + DIGEST)
            self.assertEqual(data["spec"]["ui"]["remoteEntryOci"], "ghcr.io/7k-hiroba/app/extension-ui@" + DIGEST)
            self.assertEqual(data["spec"]["ui"]["checksum"], "b" * 64)
            self.assertNotIn("@sha256:", source.read_text())

    def test_missing_digest_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ("extension.yaml", "backend.json", "ui.json", "manifest.json"):
                (root / name).write_text("{}")
            result = subprocess.run([str(ROOT / ".venv/bin/python"), str(SCRIPT), "--extension", str(root / "extension.yaml"), "--backend", str(root / "backend.json"), "--ui", str(root / "ui.json"), "--ui-manifest", str(root / "manifest.json"), "--output", str(root / "out.yaml")], text=True, capture_output=True, check=False)
            self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
