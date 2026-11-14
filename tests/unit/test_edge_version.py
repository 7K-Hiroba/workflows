from __future__ import annotations

import base64
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from tests.unit.test_validate_repository import make_valid_repo

ROOT = Path(__file__).resolve().parents[2]
SHA = "0123456789abcdef0123456789abcdef01234567"


class EdgeVersionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        make_valid_repo(self.root)
        subprocess.run([str(ROOT / ".venv/bin/python"), str(ROOT / "scripts/sync-release-please-config.py"), "--root", str(self.root)], check=True, capture_output=True)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.gh = self.bin / "gh"
        self.env = {**os.environ, "PATH": str(self.bin) + ":" + os.environ["PATH"], "GITHUB_SHA": SHA, "GITHUB_REPOSITORY": "7K-Hiroba/workflows-scaffold"}

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_open_release_pr_manifest_wins(self) -> None:
        pending = base64.b64encode(json.dumps({"packages/app": "0.2.0"}).encode()).decode()
        self.gh.write_text(f"#!/usr/bin/env bash\nif [[ \"$1\" == pr ]]; then echo release-head; else echo '{pending}'; fi\n")
        self.gh.chmod(0o755)
        result = subprocess.run(["bash", str(ROOT / "scripts/resolve-edge-version.sh"), "packages/app"], cwd=self.root, env=self.env, text=True, capture_output=True, check=False)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout.strip(), "0.2.0-0123456")

    def test_manifest_fallback_bumps_patch(self) -> None:
        self.gh.write_text("#!/usr/bin/env bash\nexit 1\n")
        self.gh.chmod(0o755)
        result = subprocess.run(["bash", str(ROOT / "scripts/resolve-edge-version.sh"), "packages/app"], cwd=self.root, env=self.env, text=True, capture_output=True, check=False)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout.strip(), "0.1.1-0123456")


if __name__ == "__main__":
    unittest.main()
