from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/prepare-chart.py"


class PrepareChartTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.chart = self.root / "chart"
        self.chart.mkdir()
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.log = self.root / "helm.log"
        helm = self.bin / "helm"
        helm.write_text(
            "#!/usr/bin/env python3\n"
            "import os, pathlib, sys\n"
            "pathlib.Path(os.environ['HELM_LOG']).write_text(' '.join(sys.argv[1:]))\n"
            "if os.environ.get('MUTATE_LOCK'):\n"
            "    pathlib.Path(sys.argv[-1], 'Chart.lock').write_text('drifted')\n"
        )
        helm.chmod(0o755)
        self.env = {**os.environ, "PATH": str(self.bin) + ":" + os.environ["PATH"], "HELM_LOG": str(self.log)}

    def tearDown(self) -> None:
        self.temp.cleanup()

    def run_prepare(self) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(ROOT / ".venv/bin/python"), str(SCRIPT), "--chart", str(self.chart)],
            env=self.env,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_chart_without_dependencies_skips_helm(self) -> None:
        (self.chart / "Chart.yaml").write_text("apiVersion: v2\nname: example\nversion: 0.1.0\n")
        result = self.run_prepare()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(self.log.exists())

    def test_locked_dependencies_are_fetched_without_metadata_drift(self) -> None:
        original = b"apiVersion: v2\nname: example\nversion: 0.1.0\ndependencies:\n  - {name: child, version: 1.2.3, repository: 'https://example.invalid'}\n"
        lock = b"dependencies:\n- {name: child, version: 1.2.3, repository: 'https://example.invalid'}\ndigest: sha256:locked\n"
        (self.chart / "Chart.yaml").write_bytes(original)
        (self.chart / "Chart.lock").write_bytes(lock)
        result = self.run_prepare()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(f"dependency update {self.chart}", self.log.read_text())
        self.assertEqual(original, (self.chart / "Chart.yaml").read_bytes())
        self.assertEqual(lock, (self.chart / "Chart.lock").read_bytes())

    def test_dependencies_require_a_lockfile(self) -> None:
        (self.chart / "Chart.yaml").write_text("apiVersion: v2\nname: example\nversion: 0.1.0\ndependencies:\n  - {name: child, version: 1.2.3}\n")
        result = self.run_prepare()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Chart.lock", result.stdout + result.stderr)
        self.assertFalse(self.log.exists())

    def test_dependency_metadata_drift_fails(self) -> None:
        (self.chart / "Chart.yaml").write_text("apiVersion: v2\nname: example\nversion: 0.1.0\ndependencies:\n  - {name: child, version: 1.2.3}\n")
        (self.chart / "Chart.lock").write_text("locked\n")
        self.env["MUTATE_LOCK"] = "true"
        result = self.run_prepare()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("metadata drift", result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
