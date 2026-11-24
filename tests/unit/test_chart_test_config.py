from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml

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
        self.assertEqual(config["install"]["values"], ["charts/workflows-scaffold/ci/kind-values.yaml"])

    def test_generic_chart_has_no_scaffold_side_effects(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "charts/example").mkdir(parents=True)
            result = self.run_config(root, "charts/example")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            config = json.loads(result.stdout)
            self.assertIsNone(config["image"])
            self.assertEqual(config["dependencies"], [])
            self.assertNotIn("upgrade", config)

    def make_lifecycle_repo(self, root: Path) -> dict:
        chart = root / "charts/example/ci"
        chart.mkdir(parents=True, exist_ok=True)
        fixture = root / "tests/chart-lifecycle/example"
        fixture.mkdir(parents=True, exist_ok=True)
        (fixture / "previous.tgz").write_bytes(b"previous")
        (fixture / "current.tgz").write_bytes(b"current")
        (fixture / "assert.sh").write_text("#!/usr/bin/env bash\nexit 0\n")
        (fixture / "assert.sh").chmod(0o755)
        declaration = {
            "schema": "inari.chart-test.v1",
            "upgrade": {
                "previousPackage": "tests/chart-lifecycle/example/previous.tgz",
                "currentPackage": "tests/chart-lifecycle/example/current.tgz",
                "timeout": "7m",
                "assertions": "tests/chart-lifecycle/example/assert.sh",
            },
        }
        (chart / "test.yaml").write_text(yaml.safe_dump(declaration, sort_keys=False))
        return declaration

    def test_valid_upgrade_declaration_is_normalized(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            declaration = self.make_lifecycle_repo(root)
            result = self.run_config(root, "charts/example")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(json.loads(result.stdout)["upgrade"], declaration["upgrade"])

    def test_upgrade_rejects_unknown_fields_and_missing_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            declaration = self.make_lifecycle_repo(root)
            path = root / "charts/example/ci/test.yaml"
            declaration["upgrade"]["unexpected"] = True
            path.write_text(yaml.safe_dump(declaration))
            result = self.run_config(root, "charts/example")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("unexpected", result.stdout + result.stderr)

            declaration = self.make_lifecycle_repo(root)
            (root / declaration["upgrade"]["currentPackage"]).unlink()
            result = self.run_config(root, "charts/example")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("currentPackage", result.stdout + result.stderr)

    def test_upgrade_rejects_unsafe_unexecutable_and_in_chart_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            declaration = self.make_lifecycle_repo(root)
            path = root / "charts/example/ci/test.yaml"
            assertion = root / declaration["upgrade"]["assertions"]
            assertion.chmod(0o644)
            result = self.run_config(root, "charts/example")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("executable", result.stdout + result.stderr)
            assertion.chmod(0o755)

            declaration["upgrade"]["previousPackage"] = "../previous.tgz"
            path.write_text(yaml.safe_dump(declaration))
            result = self.run_config(root, "charts/example")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("unsafe", result.stdout + result.stderr)

            declaration = self.make_lifecycle_repo(root)
            inside = root / "charts/example/ci/previous.tgz"
            inside.write_bytes(b"previous")
            declaration["upgrade"]["previousPackage"] = "charts/example/ci/previous.tgz"
            path.write_text(yaml.safe_dump(declaration))
            result = self.run_config(root, "charts/example")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("outside", result.stdout + result.stderr)

    def test_rejects_parent_traversal_in_dependency_and_image_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            chart = root / "charts/example/ci"
            chart.mkdir(parents=True)
            (chart / "test.yaml").write_text("schema: inari.chart-test.v1\ndependencies: [../outside.yaml]\n")
            result = self.run_config(root, "charts/example")
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("outside", result.stdout + result.stderr)
            (chart / "test.yaml").write_text("schema: inari.chart-test.v1\nimage: {context: /tmp, repository: example, tag: ci}\n")
            result = self.run_config(root, "charts/example")
            self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
