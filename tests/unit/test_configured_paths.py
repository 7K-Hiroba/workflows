from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = "a" * 40


class ConfiguredPathTests(unittest.TestCase):
    def test_package_driver_executes_the_confined_discovered_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            package = root / "catalog-packages/app"
            package.mkdir(parents=True)
            (package / "tests").mkdir()
            (package / "tests/run.sh").write_text("#!/usr/bin/env bash\necho custom-package-path > \"$ROOT_PATH/package-evidence.txt\"\n")
            bin_dir = root / "bin"
            bin_dir.mkdir()
            git = bin_dir / "git"
            git.write_text(f"#!/usr/bin/env bash\necho {SOURCE}\n")
            git.chmod(0o755)
            env = {**os.environ, "PATH": str(bin_dir) + ":" + os.environ["PATH"], "ROOT_PATH": str(root)}
            result = subprocess.run([
                "bash", str(ROOT / "scripts/test-packages.sh"), "--root", str(root), "--type", "platform-app",
                "--package", "app", "--package-path", "catalog-packages/app",
            ], env=env, text=True, capture_output=True, check=False)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual((root / "package-evidence.txt").read_text().strip(), "custom-package-path")
            evidence = json.loads((root / "evidence/package-app.json").read_text())
            self.assertEqual(evidence["sourceSha"], SOURCE)

    def test_package_driver_rejects_path_escape(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            result = subprocess.run([
                "bash", str(ROOT / "scripts/test-packages.sh"), "--root", temporary, "--type", "platform-app",
                "--package", "app", "--package-path", "../outside",
            ], text=True, capture_output=True, check=False)
            self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
