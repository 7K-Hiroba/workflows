from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "render-scaffold.sh"
SHA = "0123456789abcdef0123456789abcdef01234567"


class RenderScaffoldTests(unittest.TestCase):
    def test_renders_without_mutating_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source"
            workflow = source / ".github/workflows/ci.yml.template"
            workflow.parent.mkdir(parents=True)
            workflow.write_text("uses: 7K-Hiroba/workflows/.github/workflows/ci.yml@__WORKFLOWS_V1_SHA__ # v1.0.0\n")
            (source / "README.md").write_text("Pin __WORKFLOWS_V1_SHA__ in callers.\n")
            output = Path(tmp) / "out"
            result = subprocess.run(["bash", str(SCRIPT), "--source", str(source), "--out", str(output), "--sha", SHA], text=True, capture_output=True, check=False)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            rendered = (output / ".github/workflows/ci.yml.template").read_text()
            self.assertIn("@" + SHA, rendered)
            self.assertIn("# v1.0.0", rendered)
            self.assertNotIn("__WORKFLOWS_V1_SHA__", rendered)
            self.assertIn("__WORKFLOWS_V1_SHA__", workflow.read_text())

    def test_rejects_invalid_sha_and_existing_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source"
            source.mkdir()
            invalid = subprocess.run(["bash", str(SCRIPT), "--source", str(source), "--out", str(Path(tmp) / "out"), "--sha", "v1"], text=True, capture_output=True, check=False)
            self.assertNotEqual(invalid.returncode, 0)
            output = Path(tmp) / "existing"
            output.mkdir()
            (output / "user-work").write_text("keep")
            result = subprocess.run(["bash", str(SCRIPT), "--source", str(source), "--out", str(output), "--sha", SHA], text=True, capture_output=True, check=False)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual((output / "user-work").read_text(), "keep")


if __name__ == "__main__":
    unittest.main()
