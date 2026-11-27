from __future__ import annotations

import json
import subprocess
import sys
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
sys.path.insert(0, str(ROOT / "scripts"))
from lib.metadata import validate_release_identities  # noqa: E402


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
                for ref in (
                    f"refs/tags/{name}-v0.1.0",
                    f"refs/heads/release-please--branches--main--components--{name}",
                ):
                    checked = subprocess.run(["git", "check-ref-format", ref], check=False, capture_output=True)
                    self.assertEqual(checked.returncode, 0, ref)

    def test_direct_collision_matrix_is_kind_and_version_independent(self) -> None:
        def component(kind: str, name: str, version: str, release_component: str | None = None) -> dict:
            value = {
                "kind": kind,
                "name": name,
                "path": kind if kind in {"extension", "ui"} else f"{kind}s/{name}",
                "version": version,
            }
            if kind == "smoke":
                value["fixtureOnly"] = True
            if release_component:
                value["releaseComponent"] = release_component
            return value

        cases = []
        for left, right in (("chart", "package"), ("chart", "template"), ("package", "template")):
            cases.append((f"{left}-{right}", component(left, "shared", "0.1.0"), component(right, "shared", "0.2.0")))
        cases.extend([
            ("legacy-fixed-extension", component("extension", "extension", "0.1.0"), component("package", "extension", "0.2.0")),
            ("legacy-fixed-ui", component("ui", "ui", "0.1.0"), component("package", "ui", "0.2.0")),
            ("explicit-fixed-extension", component("extension", "extension", "0.1.0"), component("package", "app", "0.2.0", "extension")),
            ("explicit-fixed-ui", component("ui", "ui", "0.1.0"), component("chart", "app", "0.2.0", "ui")),
            ("standalone-explicit", component("smoke", "shared", "0.1.0"), component("package", "app", "0.2.0", "shared")),
            ("explicit-explicit", component("package", "app", "0.1.0", "shared"), component("template", "service", "0.2.0", "shared")),
        ])
        for name, left_template, right_template in cases:
            for versions in ("same", "different"):
                with self.subTest(name=name, versions=versions):
                    left = dict(left_template)
                    right = dict(right_template)
                    if versions == "same":
                        right["version"] = left["version"]
                        self.assertEqual(left["version"], right["version"])
                    else:
                        self.assertNotEqual(left["version"], right["version"])
                    with self.assertRaisesRegex(ValueError, "duplicate release components"):
                        validate_release_identities([left, right])

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

    def test_sync_collision_matrix_is_version_independent_and_writes_nothing(self) -> None:
        chart = "charts/workflows-scaffold/Chart.yaml"
        app = "packages/app/package.yaml"
        template = "templates/service/template.yaml"
        suite = "tests/smoke/suite.yaml"
        cases = (
            ("chart-package", "chart-package", chart, "packages/workflows-scaffold/package.yaml"),
            ("chart-template", "chart-template", chart, template),
            ("package-template", "package-template", "packages/service/package.yaml", template),
            ("legacy-fixed-extension", "legacy-extension", ".hiroba.yaml", "packages/extension/package.yaml"),
            ("legacy-fixed-ui", "legacy-ui", ".hiroba.yaml", "packages/ui/package.yaml"),
            ("explicit-fixed-extension", "explicit-extension", ".hiroba.yaml", app),
            ("explicit-fixed-ui", "explicit-ui", ".hiroba.yaml", app),
            ("standalone-explicit", "standalone-explicit", suite, app),
            ("explicit-explicit", "explicit-explicit", app, "packages/observability-pack/package.yaml"),
            ("standalone-smoke", "standalone-smoke", suite, "packages/workflows-scaffold-smoke/package.yaml"),
        )
        for name, setup, left_path, right_path in cases:
            for different_versions in (False, True):
                with self.subTest(name=name, different_versions=different_versions), tempfile.TemporaryDirectory() as tmp:
                    self.root = Path(tmp)
                    make_valid_repo(self.root)
                    if setup == "chart-package":
                        self.rename_package("workflows-scaffold")
                    elif setup == "chart-template":
                        path = self.root / chart
                        path.write_text(path.read_text().replace("name: workflows-scaffold", "name: service"))
                    elif setup == "package-template":
                        self.rename_package("service")
                    elif setup == "legacy-extension":
                        self.rename_package("extension")
                    elif setup == "legacy-ui":
                        self.rename_package("ui")
                    elif setup == "explicit-extension":
                        self.release_components({"packages/app": "extension"})
                    elif setup == "explicit-ui":
                        self.release_components({"packages/app": "ui"})
                    elif setup == "standalone-explicit":
                        use_fixture_only_smoke(self.root)
                        self.release_components({"tests/smoke": "shared", "packages/app": "shared"})
                    elif setup == "explicit-explicit":
                        self.release_components({"packages/app": "shared", "packages/observability-pack": "shared"})
                    else:
                        use_fixture_only_smoke(self.root)
                        self.rename_package("workflows-scaffold-smoke")
                    if different_versions:
                        path = self.root / right_path
                        original = path.read_text()
                        updated = original.replace("version: 0.1.0", "version: 0.2.0", 1)
                        self.assertNotEqual(original, updated)
                        path.write_text(updated)

                    def version(relative: str) -> str:
                        data = yaml.safe_load((self.root / relative).read_text())
                        if relative == ".hiroba.yaml":
                            kind = "ui" if "ui" in name else "extension"
                            return str(data["components"][kind]["version"])
                        if relative == suite:
                            return str(data["target"]["version"])
                        return str(data["version"])

                    if different_versions:
                        self.assertNotEqual(version(left_path), version(right_path))
                    else:
                        self.assertEqual(version(left_path), version(right_path))
                    result = self.assert_sync_fails_without_writes()
                    self.assertIn("duplicate release components", result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
