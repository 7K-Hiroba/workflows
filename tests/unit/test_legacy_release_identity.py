from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml

from tests.unit.test_release_metadata import tree_bytes, write_marked_versions
from tests.unit.test_validate_repository import make_valid_repo, use_fixture_only_smoke

ROOT = Path(__file__).resolve().parents[2]
PYTHON = ROOT / ".venv" / "bin" / "python"
if not PYTHON.exists():
    PYTHON = Path("python3")


class LegacyReleaseIdentityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        make_valid_repo(self.root)
        write_marked_versions(self.root)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def sync(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(PYTHON), str(ROOT / "scripts/sync-release-please-config.py"), "--root", str(self.root), *args],
            text=True,
            capture_output=True,
            check=False,
        )

    def config(self) -> dict:
        return json.loads((self.root / "release-please-config.json").read_text())

    def release_components(self, values: dict[str, str]) -> None:
        path = self.root / ".hiroba.yaml"
        data = yaml.safe_load(path.read_text())
        data["releaseComponents"] = values
        path.write_text(yaml.safe_dump(data, sort_keys=False))

    def rename_package(self, name: str) -> None:
        source = self.root / "packages/app"
        target = self.root / "packages" / name
        source.rename(target)

    def assert_sync_fails_without_writes(self) -> subprocess.CompletedProcess[str]:
        before = tree_bytes(self.root)
        result = self.sync()
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(tree_bytes(self.root), before)
        return result

    def test_legacy_components_and_package_options_are_deterministic(self) -> None:
        result = self.sync()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        config = self.config()
        expected = {
            "charts/workflows-scaffold": "workflows-scaffold",
            "packages/app": "app",
            "packages/admission-example": "admission-example",
            "packages/observability-pack": "observability-pack",
            "templates/service": "service",
            "extension": "extension",
            "ui": "ui",
        }
        self.assertIs(config["include-v-in-tag"], True)
        self.assertEqual(config["tag-separator"], "-v")
        for path, component in expected.items():
            self.assertEqual(config["packages"][path].get("component"), component)
            self.assertIs(config["packages"][path]["include-v-in-tag"], False)
        before = tree_bytes(self.root)
        self.assertEqual(self.sync().returncode, 0)
        self.assertEqual(self.sync("--check").returncode, 0)
        self.assertEqual(tree_bytes(self.root), before)

    def test_valid_legacy_names_are_preserved(self) -> None:
        for name in ("Legacy_Name", "legacy.name", "_legacy", "legacy.locks", "legacy-name"):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                self.root = Path(tmp)
                make_valid_repo(self.root)
                self.rename_package(name)
                result = self.sync()
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                package = self.config()["packages"][f"packages/{name}"]
                self.assertEqual(package.get("component"), name)
                self.assertIs(package["include-v-in-tag"], False)

    def test_invalid_legacy_names_fail_without_writes(self) -> None:
        for name in ("bad..name", "bad--components--name", "-bad", "bad@name", "bad name", "bad.", "bad.lock"):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                self.root = Path(tmp)
                make_valid_repo(self.root)
                self.rename_package(name)
                result = self.assert_sync_fails_without_writes()
                self.assertIn("component", (result.stdout + result.stderr).lower())

    def test_explicit_delimiter_fails_without_writes_and_safe_mapping_passes(self) -> None:
        self.release_components({"packages/app": "package--components--bad"})
        result = self.assert_sync_fails_without_writes()
        self.assertIn("--components--", result.stdout + result.stderr)
        self.release_components({"packages/app": "package-safe-name"})
        result = self.sync()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.config()["packages"]["packages/app"].get("component"), "package-safe-name")

    def test_chart_package_collision_is_version_independent_and_kind_qualified_resolution_passes(self) -> None:
        for different_versions in (False, True):
            with self.subTest(different_versions=different_versions), tempfile.TemporaryDirectory() as tmp:
                self.root = Path(tmp)
                make_valid_repo(self.root)
                self.rename_package("workflows-scaffold")
                if different_versions:
                    chart = self.root / "charts/workflows-scaffold/Chart.yaml"
                    chart.write_text(chart.read_text().replace("version: 0.1.0", "version: 0.2.0"))
                result = self.assert_sync_fails_without_writes()
                self.assertIn("workflows-scaffold", result.stdout + result.stderr)
                self.release_components({
                    "charts/workflows-scaffold": "chart-workflows-scaffold",
                    "packages/workflows-scaffold": "package-workflows-scaffold",
                })
                result = self.sync()
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                config = self.config()
                self.assertEqual(config["packages"]["charts/workflows-scaffold"].get("component"), "chart-workflows-scaffold")
                self.assertEqual(config["packages"]["packages/workflows-scaffold"].get("component"), "package-workflows-scaffold")

    def test_fixed_explicit_and_standalone_smoke_collisions_fail_without_writes(self) -> None:
        cases = (
            ("fixed-explicit", {"packages/app": "extension"}, False),
            ("fixed-explicit-different-version", {"packages/app": "extension"}, True),
            ("explicit-explicit", {"packages/app": "package-shared", "packages/observability-pack": "package-shared"}, False),
            ("explicit-explicit-different-version", {"packages/app": "package-shared", "packages/observability-pack": "package-shared"}, True),
        )
        for name, mappings, different_versions in cases:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                self.root = Path(tmp)
                make_valid_repo(self.root)
                if different_versions:
                    package = self.root / "packages/app/package.yaml"
                    package.write_text(package.read_text().replace("version: 0.1.0", "version: 0.2.0"))
                self.release_components(mappings)
                self.assert_sync_fails_without_writes()

        for different_versions in (False, True):
            with self.subTest(kind="standalone-smoke", different_versions=different_versions), tempfile.TemporaryDirectory() as tmp:
                self.root = Path(tmp)
                make_valid_repo(self.root)
                use_fixture_only_smoke(self.root)
                self.rename_package("workflows-scaffold-smoke")
                if different_versions:
                    package = self.root / "packages/workflows-scaffold-smoke/package.yaml"
                    package.write_text(package.read_text().replace("version: 0.1.0", "version: 0.2.0"))
                self.assert_sync_fails_without_writes()


if __name__ == "__main__":
    unittest.main()
