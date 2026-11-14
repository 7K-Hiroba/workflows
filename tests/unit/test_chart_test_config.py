from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/chart-test-config.py"


class ChartTestConfigTests(unittest.TestCase):
    def run_config(self, root: Path, chart: str = "charts/workflows-scaffold") -> subprocess.CompletedProcess[str]:
        return subprocess.run([str(ROOT / ".venv/bin/python"), str(SCRIPT), "--root", str(root), "--chart", chart], text=True, capture_output=True, check=False)

    def test_scaffold_owns_image_dependency_and_install_declarations(self) -> None:
        result = self.run_config(ROOT / "scaffold")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        config = json.loads(result.stdout)
        self.assertEqual(config["image"], {"context": "extension", "repository": "workflows-scaffold", "tag": "ci"})
        self.assertEqual(config["dependencies"], ["packages/observability-pack/tests/deps/prometheusrule-crd.yaml"])
        self.assertEqual(config["install"]["timeout"], "5m")

    def test_generic_chart_has_no_scaffold_side_effects(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "charts/example").mkdir(parents=True)
            result = self.run_config(root, "charts/example")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            config = json.loads(result.stdout)
            self.assertIsNone(config["image"])
            self.assertEqual(config["dependencies"], [])

    def test_rejects_parent_traversal_in_dependency_and_image_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            chart = root / "charts/example/ci"
            chart.mkdir(parents=True)
            (chart / "test.yaml").write_text("schema: inari.chart-test.v1\ndependencies: [../outside.yaml]\n")
            result = self.run_config(root, "charts/example")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("escapes", result.stdout + result.stderr)
            (chart / "test.yaml").write_text("schema: inari.chart-test.v1\nimage: {context: /tmp, repository: example, tag: ci}\n")
            result = self.run_config(root, "charts/example")
            self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
