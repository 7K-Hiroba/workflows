from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCAFFOLD = ROOT / "scaffold"
PYTHON = ROOT / ".venv" / "bin" / "python"
if not PYTHON.exists():
    PYTHON = Path("python3")


class ScaffoldContractTests(unittest.TestCase):
    def run_script(self, name: str, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run([str(PYTHON), str(ROOT / "scripts" / name), "--root", str(SCAFFOLD), *args], text=True, capture_output=True, check=False)

    def test_scaffold_validates_against_registry(self) -> None:
        result = self.run_script("validate-repository.py", "--registry", str(ROOT / "tests/fixtures/app-registry.yaml"))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_generated_outputs_are_in_sync(self) -> None:
        for script in ("build-indexes.py", "sync-release-please-config.py", "render-observability.py"):
            with self.subTest(script=script):
                result = self.run_script(script, "--check")
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_component_matrix_is_complete(self) -> None:
        result = self.run_script("discover-components.py", "--all")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        plan = json.loads(result.stdout)
        kinds = {component["kind"] for component in plan["components"]}
        self.assertEqual(kinds, {"extension", "ui", "chart", "package", "template", "smoke"})

    def test_caller_templates_are_pin_safe(self) -> None:
        result = self.run_script("check-workflow-pins.py")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        rendered = self.run_script("check-workflow-pins.py", "--require-rendered")
        self.assertNotEqual(rendered.returncode, 0)

    def test_ui_uses_only_public_sdk_and_canonical_build(self) -> None:
        package = json.loads((SCAFFOLD / "ui/package.json").read_text())
        self.assertEqual(package["dependencies"]["@7k-inari/ui-plugin-sdk"], "0.1.7")
        self.assertEqual(package["scripts"]["build"], "inari-ui-ext build")
        self.assertFalse((SCAFFOLD / "ui/webpack.config.mjs").exists())
        source = "\n".join(path.read_text() for path in (SCAFFOLD / "ui").rglob("*.ts*") if "node_modules" not in path.parts)
        self.assertNotIn("build-sdk", source)
        self.assertNotIn("postinstall", source)


if __name__ == "__main__":
    unittest.main()
