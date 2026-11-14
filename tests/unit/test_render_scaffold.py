from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "render-scaffold.sh"
LINT = ROOT / "scripts" / "lint-rendered-workflows.sh"
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

    def test_actionlint_covers_every_rendered_consumer_template(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "out"
            rendered = subprocess.run(["bash", str(SCRIPT), "--source", str(ROOT / "scaffold"), "--out", str(output), "--sha", SHA], text=True, capture_output=True, check=False)
            self.assertEqual(rendered.returncode, 0, rendered.stdout + rendered.stderr)
            go_path = subprocess.check_output(["go", "env", "GOPATH"], text=True).strip()
            env = {**os.environ, "PATH": str(Path(go_path) / "bin") + ":" + os.environ["PATH"]}
            valid = subprocess.run(["bash", str(LINT), "--root", str(output)], env=env, text=True, capture_output=True, check=False)
            self.assertEqual(valid.returncode, 0, valid.stdout + valid.stderr)
            target = output / ".github/workflows/test-packages.yml.template"
            target.write_text(target.read_text() + "    cache-mode: read\n")
            invalid = subprocess.run(["bash", str(LINT), "--root", str(output)], env=env, text=True, capture_output=True, check=False)
            self.assertNotEqual(invalid.returncode, 0)
            self.assertIn("cache-mode", invalid.stdout + invalid.stderr)

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
