from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml

from tests.unit.test_validate_repository import make_valid_repo, use_fixture_only_smoke, write

ROOT = Path(__file__).resolve().parents[2]
PYTHON = ROOT / ".venv" / "bin" / "python"
if not PYTHON.exists():
    PYTHON = Path("python3")

BACKEND_VERSION = "extension/internal/extplugin/version.go"
UI_VERSION = "ui/src/index.tsx"
BACKEND_ROOT_EXTRA = {"type": "generic", "path": "/extension.yaml"}
BACKEND_YAML_EXTRA = {"type": "yaml", "path": "/.hiroba.yaml", "jsonpath": "$.components.extension.version"}
UI_YAML_EXTRA = {"type": "yaml", "path": "/.hiroba.yaml", "jsonpath": "$.components.ui.version"}


def run_script(root: Path, name: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(PYTHON), str(ROOT / "scripts" / name), "--root", str(root), *args],
        text=True,
        capture_output=True,
        check=False,
    )


def write_marked_versions(root: Path, backend: str = "0.1.0", ui: str = "0.1.0") -> None:
    write(root, BACKEND_VERSION, f'package extplugin\n\nconst Version = "{backend}" // x-release-please-version\n')
    write(root, UI_VERSION, f"export default createExtension({{\n  manifest: {{\n    version: '{ui}', // x-release-please-version\n  }},\n}});\n")


def set_component_versions(root: Path, backend: str | None = None, ui: str | None = None) -> None:
    path = root / ".hiroba.yaml"
    config = yaml.safe_load(path.read_text())
    if backend is not None:
        config["components"]["extension"]["version"] = backend
    if ui is not None:
        config["components"]["ui"]["version"] = ui
    path.write_text(yaml.safe_dump(config, sort_keys=False))


def tree_bytes(root: Path) -> dict[str, bytes]:
    return {str(path.relative_to(root)): path.read_bytes() for path in root.rglob("*") if path.is_file()}


def changed_paths(before: dict[str, bytes], after: dict[str, bytes]) -> set[str]:
    return {path for path in before.keys() | after.keys() if before.get(path) != after.get(path)}


class ReleaseMetadataTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        make_valid_repo(self.root)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def run_script(self, name: str, *args: str) -> subprocess.CompletedProcess[str]:
        return run_script(self.root, name, *args)

    def test_discovers_all_components_and_target_scoped_smoke(self) -> None:
        result = self.run_script("discover-components.py", "--all")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        payload = json.loads(result.stdout)
        kinds = {item["kind"] for item in payload["components"]}
        self.assertEqual(kinds, {"extension", "ui", "chart", "package", "template", "smoke"})
        smoke = next(item for item in payload["components"] if item["kind"] == "smoke")
        self.assertEqual(smoke["version"], "0.1.0")
        self.assertEqual(smoke["targetComponent"], "charts/workflows-scaffold")
        names = [item["name"] for item in payload["components"]]
        self.assertEqual(names, sorted(names))

    def test_discovers_standalone_fixture_only_smoke(self) -> None:
        use_fixture_only_smoke(self.root)
        result = self.run_script("discover-components.py", "--all")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        smoke = next(item for item in json.loads(result.stdout)["components"] if item["kind"] == "smoke")
        self.assertEqual(smoke["name"], "workflows-scaffold-smoke")
        self.assertEqual(smoke["targetAdapter"], "manifests")
        self.assertTrue(smoke["fixtureOnly"])
        self.assertEqual(smoke["executableProfiles"], ["ci"])
        self.assertEqual(smoke["evidenceScope"], "fixture")
        self.assertFalse(smoke["appEvidenceEligible"])
        self.assertNotIn("targetComponent", smoke)

    def test_standalone_fixture_smoke_has_independent_release_metadata(self) -> None:
        use_fixture_only_smoke(self.root)
        result = self.run_script("sync-release-please-config.py")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        config = json.loads((self.root / "release-please-config.json").read_text())
        smoke = config["packages"]["tests/smoke"]
        self.assertEqual(smoke["release-type"], "simple")
        self.assertEqual(smoke["component"], "workflows-scaffold-smoke")
        self.assertIn("suite.yaml", smoke["extra-files"])
        manifest = json.loads((self.root / ".release-please-manifest.json").read_text())
        self.assertEqual(manifest["tests/smoke"], "0.1.0")

    def test_standalone_smoke_uses_opt_in_release_component(self) -> None:
        use_fixture_only_smoke(self.root)
        config_path = self.root / ".hiroba.yaml"
        config = yaml.safe_load(config_path.read_text())
        config["releaseComponents"] = {"tests/smoke": "smoke-workflows-scaffold-smoke"}
        config_path.write_text(yaml.safe_dump(config, sort_keys=False))
        result = self.run_script("sync-release-please-config.py")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        release_please = json.loads((self.root / "release-please-config.json").read_text())
        self.assertEqual(release_please["packages"]["tests/smoke"]["component"], "smoke-workflows-scaffold-smoke")

    def test_release_components_reject_unknown_paths_and_artifact_bound_smoke(self) -> None:
        for release_components, expected in (
            ({"packages/missing": "package-missing"}, "unknown component"),
            ({"tests/smoke": "smoke-custom"}, "inherits its target"),
            ({"extension": "backend-custom"}, "fixed extension/UI"),
        ):
            with self.subTest(release_components=release_components):
                config_path = self.root / ".hiroba.yaml"
                config = yaml.safe_load(config_path.read_text())
                config["releaseComponents"] = release_components
                config_path.write_text(yaml.safe_dump(config, sort_keys=False))
                result = self.run_script("discover-components.py", "--all")
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(expected, result.stdout + result.stderr)

    def test_discovery_can_filter_changed_files(self) -> None:
        changed = self.root / "changed.txt"
        changed.write_text("packages/app/package.yaml\n")
        result = self.run_script("discover-components.py", "--changed-files", str(changed))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        components = json.loads(result.stdout)["components"]
        self.assertEqual(len(components), 1)
        self.assertEqual(components[0]["name"], "app")

    def test_discovery_honors_non_default_component_layout(self) -> None:
        for old, new in (("extension", "backend"), ("ui", "frontend"), ("charts", "helm"), ("packages", "catalog-packages"), ("templates", "scaffolds")):
            target = self.root / new
            target.parent.mkdir(parents=True, exist_ok=True)
            (self.root / old).rename(target)
        smoke_target = self.root / "verification/smoke"
        smoke_target.parent.mkdir()
        (self.root / "tests/smoke").rename(smoke_target)
        config_path = self.root / ".hiroba.yaml"
        config = yaml.safe_load(config_path.read_text())
        config["components"].update({
            "extension": {"path": "backend", "version": "0.1.0"},
            "ui": {"path": "frontend", "version": "0.1.0"},
            "chartsRoot": "helm",
            "packagesRoot": "catalog-packages",
            "templatesRoot": "scaffolds",
        })
        config["observability"]["chart"] = "helm/workflows-scaffold"
        config["observability"]["package"] = "catalog-packages/observability-pack"
        config["smoke"] = {"path": "verification/smoke", "targetComponent": "helm/workflows-scaffold"}
        config_path.write_text(yaml.safe_dump(config, sort_keys=False))
        suite_path = smoke_target / "suite.yaml"
        suite = yaml.safe_load(suite_path.read_text())
        suite["target"]["component"] = "helm/workflows-scaffold"
        suite_path.write_text(yaml.safe_dump(suite, sort_keys=False))
        result = self.run_script("discover-components.py", "--all")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        components = json.loads(result.stdout)["components"]
        paths = {item["kind"]: item["path"] for item in components if item["kind"] in {"extension", "ui", "chart", "template", "smoke"}}
        self.assertEqual(paths["extension"], "backend")
        self.assertEqual(paths["ui"], "frontend")
        self.assertEqual(paths["chart"], "helm/workflows-scaffold")
        self.assertEqual(paths["template"], "scaffolds/service")
        self.assertEqual(paths["smoke"], "verification/smoke")
        self.assertIn("catalog-packages/app", {item["path"] for item in components if item["kind"] == "package"})

    def test_source_indexes_are_deterministic_and_check_is_no_write(self) -> None:
        first = self.run_script("build-indexes.py")
        self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
        catalog = yaml.safe_load((self.root / "catalog.yaml").read_text())
        self.assertEqual([entry["name"] for entry in catalog["packages"]], ["admission-example", "app", "observability-pack"])
        app = next(entry for entry in catalog["packages"] if entry["name"] == "app")
        self.assertEqual(app["ociRef"], "ghcr.io/7k-hiroba/workflows-scaffold/catalog/app:0.1.0")
        self.assertEqual(app["channelRef"], "ghcr.io/7k-hiroba/workflows-scaffold/catalog/app:incubating")
        self.assertNotIn("digest", app)
        templates = yaml.safe_load((self.root / "templates.yaml").read_text())
        self.assertEqual(templates["templates"][0]["ociRef"], "ghcr.io/7k-hiroba/workflows-scaffold/templates/service:0.1.0")
        before = (self.root / "catalog.yaml").read_bytes()
        self.assertEqual(self.run_script("build-indexes.py", "--check").returncode, 0)
        (self.root / "catalog.yaml").write_text("stale: true\n")
        stale = self.run_script("build-indexes.py", "--check")
        self.assertNotEqual(stale.returncode, 0)
        self.assertEqual((self.root / "catalog.yaml").read_text(), "stale: true\n")
        self.assertNotEqual((self.root / "catalog.yaml").read_bytes(), before)

    def test_release_indexes_require_and_embed_exact_digests(self) -> None:
        evidence = self.root / "evidence.json"
        evidence.write_text(json.dumps({"artifacts": {}}))
        missing = self.run_script("build-indexes.py", "--release-evidence", str(evidence))
        self.assertNotEqual(missing.returncode, 0)
        artifacts = {}
        for kind, name, path in (
            ("catalog", "admission-example", "catalog/admission-example"),
            ("catalog", "app", "catalog/app"),
            ("catalog", "observability-pack", "catalog/observability-pack"),
            ("template", "service", "templates/service"),
        ):
            artifacts[f"{kind}/{name}"] = {
                "repository": f"ghcr.io/7k-hiroba/workflows-scaffold/{'catalog' if kind == 'catalog' else 'templates'}/{name}",
                "digest": "sha256:" + name.encode().hex().ljust(64, "0")[:64],
                "mediaType": "application/vnd.inari.template.v1" if kind == "template" else "application/vnd.inari.catalog.package.v1+yaml",
                "sourceSha": "a" * 40,
                "signature": {"verified": True},
                "provenance": {"verified": True},
                "testEvidence": {"status": "passed"},
            }
        evidence.write_text(json.dumps({"sourceSha": "a" * 40, "artifacts": artifacts}))
        released = self.run_script("build-indexes.py", "--release-evidence", str(evidence))
        self.assertEqual(released.returncode, 0, released.stdout + released.stderr)
        catalog = yaml.safe_load((self.root / "catalog.yaml").read_text())
        for entry in catalog["packages"]:
            self.assertIn("@sha256:", entry["ociRef"])
            self.assertEqual(entry["sourceSha"], "a" * 40)
            self.assertEqual(entry["testEvidence"]["status"], "passed")
        prefix = "ghcr.io/7k-hiroba/workflows/ci"
        for key, artifact in artifacts.items():
            kind, name = key.split("/", 1)
            directory = "catalog" if kind == "catalog" else "templates"
            artifact["repository"] = f"{prefix}/workflows-scaffold/{directory}/{name}"
        evidence.write_text(json.dumps({"sourceSha": "a" * 40, "artifacts": artifacts}))
        custom = self.run_script("build-indexes.py", "--release-evidence", str(evidence), "--registry-prefix", prefix)
        self.assertEqual(custom.returncode, 0, custom.stdout + custom.stderr)
        catalog = yaml.safe_load((self.root / "catalog.yaml").read_text())
        self.assertTrue(all(entry["ociRef"].startswith(prefix + "/") for entry in catalog["packages"]))
        artifacts["catalog/app"]["repository"] = "ghcr.io/7k-hiroba/untrusted/catalog/app"
        evidence.write_text(json.dumps({"sourceSha": "a" * 40, "artifacts": artifacts}))
        mismatch = self.run_script("build-indexes.py", "--release-evidence", str(evidence), "--registry-prefix", prefix)
        self.assertNotEqual(mismatch.returncode, 0)
        self.assertIn("repository", (mismatch.stdout + mismatch.stderr).lower())

    def test_edge_indexes_use_verified_prerelease_tags_and_edge_channels(self) -> None:
        artifacts = {}
        for kind, name in (("catalog", "admission-example"), ("catalog", "app"), ("catalog", "observability-pack"), ("template", "service")):
            directory = "catalog" if kind == "catalog" else "templates"
            artifacts[f"{kind}/{name}"] = {
                "repository": f"ghcr.io/7k-hiroba/workflows-scaffold/{directory}/{name}",
                "digest": "sha256:" + name.encode().hex().ljust(64, "0")[:64],
                "mediaType": "application/vnd.inari.template.v1" if kind == "template" else "application/vnd.inari.catalog.package.v1+yaml",
                "sourceSha": "a" * 40,
                "tag": "0.2.0-0123456",
                "channel": "edge",
                "signature": {"verified": True},
                "provenance": {"verified": True},
                "testEvidence": {"status": "passed"},
            }
        evidence = self.root / "edge-evidence.json"
        evidence.write_text(json.dumps({"sourceSha": "a" * 40, "artifacts": artifacts}))
        result = self.run_script("build-indexes.py", "--release-evidence", str(evidence))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        catalog = yaml.safe_load((self.root / "catalog.yaml").read_text())
        for entry in catalog["packages"]:
            self.assertEqual(entry["version"], "0.2.0-0123456")
            self.assertEqual(entry["channel"], "edge")
            self.assertTrue(entry["channelRef"].endswith(":edge"))

    def test_release_please_config_covers_every_component(self) -> None:
        result = self.run_script("sync-release-please-config.py")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        config = json.loads((self.root / "release-please-config.json").read_text())
        expected = {"extension", "ui", "charts/workflows-scaffold", "packages/admission-example", "packages/app", "packages/observability-pack", "templates/service"}
        self.assertEqual(set(config["packages"]), expected)
        expected_components = {
            "extension": "extension",
            "ui": "ui",
            "charts/workflows-scaffold": "workflows-scaffold",
            "packages/admission-example": "admission-example",
            "packages/app": "app",
            "packages/observability-pack": "observability-pack",
            "templates/service": "service",
        }
        self.assertIs(config["include-v-in-tag"], True)
        self.assertEqual(config["tag-separator"], "-v")
        for path, package in config["packages"].items():
            self.assertEqual(package.get("component"), expected_components[path])
            self.assertIs(package["include-v-in-tag"], False)
        self.assertEqual(config["packages"]["extension"]["release-type"], "go")
        self.assertEqual(config["packages"]["ui"]["release-type"], "node")
        self.assertIn("Chart.yaml", config["packages"]["charts/workflows-scaffold"]["extra-files"])
        manifest = json.loads((self.root / ".release-please-manifest.json").read_text())
        self.assertEqual(set(manifest), expected)
        self.assertEqual(self.run_script("sync-release-please-config.py", "--check").returncode, 0)
        (self.root / "release-please-config.json").write_text("{}\n")
        drift = self.run_script("sync-release-please-config.py", "--check")
        self.assertNotEqual(drift.returncode, 0)
        self.assertEqual((self.root / "release-please-config.json").read_text(), "{}\n")


class MarkedReleaseVersionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        make_valid_repo(self.root)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def sync(self, *args: str) -> subprocess.CompletedProcess[str]:
        return run_script(self.root, "sync-release-please-config.py", *args)

    def test_current_versions_are_noop_and_extras_are_additive_and_idempotent(self) -> None:
        write_marked_versions(self.root)
        result = self.sync()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        config = json.loads((self.root / "release-please-config.json").read_text())
        extension = config["packages"]["extension"]
        ui = config["packages"]["ui"]
        self.assertEqual(extension["release-type"], "go")
        self.assertEqual(ui["release-type"], "node")
        self.assertEqual(extension.get("component"), "extension")
        self.assertEqual(ui.get("component"), "ui")
        self.assertIs(extension["include-v-in-tag"], False)
        self.assertIs(ui["include-v-in-tag"], False)
        self.assertEqual(extension["extra-files"], [BACKEND_ROOT_EXTRA, "internal/extplugin/version.go", BACKEND_YAML_EXTRA])
        self.assertEqual(ui["extra-files"], ["src/index.tsx", UI_YAML_EXTRA])
        self.assertNotIn("plugins", config)
        for package in config["packages"].values():
            self.assertNotIn("release-as", package)

        before = tree_bytes(self.root)
        repeated = self.sync()
        self.assertEqual(repeated.returncode, 0, repeated.stdout + repeated.stderr)
        self.assertEqual(tree_bytes(self.root), before)
        checked = self.sync("--check")
        self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)
        self.assertEqual(tree_bytes(self.root), before)

    def test_next_versions_update_backend_and_ui_independently(self) -> None:
        write_marked_versions(self.root)
        self.assertEqual(self.sync().returncode, 0)

        set_component_versions(self.root, backend="0.1.2")
        backend_only = self.sync()
        self.assertEqual(backend_only.returncode, 0, backend_only.stdout + backend_only.stderr)
        self.assertIn('const Version = "0.1.2"', (self.root / BACKEND_VERSION).read_text())
        self.assertIn("version: '0.1.0'", (self.root / UI_VERSION).read_text())
        manifest = json.loads((self.root / ".release-please-manifest.json").read_text())
        self.assertEqual(manifest["extension"], "0.1.2")
        self.assertEqual(manifest["ui"], "0.1.0")

        set_component_versions(self.root, ui="0.4.0")
        yaml_before = yaml.safe_load((self.root / ".hiroba.yaml").read_text())
        before = tree_bytes(self.root)
        ui_only = self.sync()
        self.assertEqual(ui_only.returncode, 0, ui_only.stdout + ui_only.stderr)
        self.assertIn('const Version = "0.1.2"', (self.root / BACKEND_VERSION).read_text())
        self.assertIn("version: '0.4.0'", (self.root / UI_VERSION).read_text())
        manifest = json.loads((self.root / ".release-please-manifest.json").read_text())
        self.assertEqual(manifest["extension"], "0.1.2")
        self.assertEqual(manifest["ui"], "0.4.0")
        self.assertNotEqual(manifest["extension"], manifest["ui"])
        self.assertEqual(changed_paths(before, tree_bytes(self.root)), {UI_VERSION, ".release-please-manifest.json"})
        self.assertEqual(yaml.safe_load((self.root / ".hiroba.yaml").read_text()), yaml_before)
        self.assertEqual(self.sync("--check").returncode, 0)

    def test_version_updates_preserve_source_formatting_and_final_newline_state(self) -> None:
        write(
            self.root,
            BACKEND_VERSION,
            'package extplugin\n\nconst (\n\tName = "example"\n\tVersion = "0.1.0" // x-release-please-version\n)',
        )
        write(
            self.root,
            UI_VERSION,
            'export default createExtension({\n  manifest: {\n    // retain this comment\n    version: "0.1.0", // x-release-please-version\n  },\n});',
        )
        set_component_versions(self.root, backend="0.2.0", ui="0.3.0")
        result = self.sync()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(
            (self.root / BACKEND_VERSION).read_bytes(),
            b'package extplugin\n\nconst (\n\tName = "example"\n\tVersion = "0.2.0" // x-release-please-version\n)',
        )
        self.assertEqual(
            (self.root / UI_VERSION).read_bytes(),
            b'export default createExtension({\n  manifest: {\n    // retain this comment\n    version: "0.3.0", // x-release-please-version\n  },\n});',
        )

    def test_manual_source_drift_fails_check_and_repairs_only_that_file(self) -> None:
        write_marked_versions(self.root)
        self.assertEqual(self.sync().returncode, 0)
        path = self.root / BACKEND_VERSION
        path.write_text(path.read_text().replace('Version = "0.1.0"', 'Version = "9.9.9"'))
        before = tree_bytes(self.root)
        drift = self.sync("--check")
        self.assertNotEqual(drift.returncode, 0)
        self.assertIn(BACKEND_VERSION, drift.stdout + drift.stderr)
        self.assertEqual(tree_bytes(self.root), before)

        repaired = self.sync()
        self.assertEqual(repaired.returncode, 0, repaired.stdout + repaired.stderr)
        self.assertEqual(changed_paths(before, tree_bytes(self.root)), {BACKEND_VERSION})
        self.assertEqual(self.sync("--check").returncode, 0)

        manifest_path = self.root / ".release-please-manifest.json"
        manifest_path.write_text("{}\n")
        before = tree_bytes(self.root)
        manifest_drift = self.sync("--check")
        self.assertNotEqual(manifest_drift.returncode, 0)
        self.assertEqual(tree_bytes(self.root), before)

    def test_legacy_unmarked_sources_remain_unmanaged(self) -> None:
        write(self.root, BACKEND_VERSION, 'package extplugin\n\nconst Version = "9.9.9"\n')
        write(self.root, UI_VERSION, "export default {manifest: {version: '8.8.8'}};\n")
        before_backend = (self.root / BACKEND_VERSION).read_bytes()
        before_ui = (self.root / UI_VERSION).read_bytes()
        result = self.sync()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        config = json.loads((self.root / "release-please-config.json").read_text())
        self.assertEqual(config["packages"]["extension"]["extra-files"], [BACKEND_ROOT_EXTRA, BACKEND_YAML_EXTRA])
        self.assertEqual(config["packages"]["ui"]["extra-files"], [UI_YAML_EXTRA])
        self.assertEqual((self.root / BACKEND_VERSION).read_bytes(), before_backend)
        self.assertEqual((self.root / UI_VERSION).read_bytes(), before_ui)

    def test_invalid_root_extension_markers_fail_without_any_writes(self) -> None:
        for case in ("missing-file", "missing-marker", "duplicate-marker", "malformed-marker", "invalid-utf8"):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                make_valid_repo(root)
                write_marked_versions(root)
                path = root / "extension.yaml"
                if case == "missing-file":
                    path.unlink()
                elif case == "missing-marker":
                    path.write_text(path.read_text().replace(" # x-release-please-version", ""))
                elif case == "duplicate-marker":
                    path.write_text(path.read_text() + "version: 0.2.0 # x-release-please-version\n")
                elif case == "invalid-utf8":
                    path.write_bytes(path.read_bytes() + b"\xff")
                else:
                    path.write_text(path.read_text().replace("version: 0.1.0", "version: latest"))
                before = tree_bytes(root)
                result = run_script(root, "sync-release-please-config.py")
                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("extension.yaml", result.stdout + result.stderr)
                self.assertIn("x-release-please-version", result.stdout + result.stderr)
                if case == "invalid-utf8":
                    self.assertIn("valid UTF-8", result.stdout + result.stderr)
                self.assertEqual(tree_bytes(root), before)

    def test_malformed_marked_declarations_fail_without_any_writes(self) -> None:
        cases = {
            "missing_value": (BACKEND_VERSION, b'package extplugin\n\nconst Version = "" // x-release-please-version\n'),
            "wrong_declaration": (BACKEND_VERSION, b'package extplugin\n\nconst Other = "0.1.0" // x-release-please-version\n'),
            "ambiguous_declarations": (
                BACKEND_VERSION,
                b'package extplugin\n\nconst Version = "0.1.0" // x-release-please-version\nconst Version = "0.2.0" // x-release-please-version\n',
            ),
            "invalid_semver": (UI_VERSION, b"export default {manifest: {version: 'latest', // x-release-please-version\n}};\n"),
            "invalid_utf8": (BACKEND_VERSION, b'package extplugin\n\nconst Version = "0.1.0" // x-release-please-version\n\xff'),
        }
        for name, (relative, content) in cases.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                make_valid_repo(root)
                write_marked_versions(root)
                path = root / relative
                path.write_bytes(content)
                before = tree_bytes(root)
                result = run_script(root, "sync-release-please-config.py")
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(tree_bytes(root), before)

    def test_missing_or_invalid_canonical_versions_fail_without_writes(self) -> None:
        for kind in ("extension", "ui"):
            for invalid in (None, "not-semver"):
                with self.subTest(kind=kind, invalid=invalid), tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    make_valid_repo(root)
                    write_marked_versions(root)
                    path = root / ".hiroba.yaml"
                    config = yaml.safe_load(path.read_text())
                    if invalid is None:
                        del config["components"][kind]["version"]
                    else:
                        config["components"][kind]["version"] = invalid
                    path.write_text(yaml.safe_dump(config, sort_keys=False))
                    before = tree_bytes(root)
                    result = run_script(root, "sync-release-please-config.py")
                    self.assertNotEqual(result.returncode, 0)
                    self.assertEqual(tree_bytes(root), before)

    def test_previously_managed_file_cannot_disappear_or_lose_its_marker(self) -> None:
        for mutation in ("delete", "unmark"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                make_valid_repo(root)
                write_marked_versions(root)
                self.assertEqual(run_script(root, "sync-release-please-config.py").returncode, 0)
                path = root / BACKEND_VERSION
                if mutation == "delete":
                    path.unlink()
                else:
                    path.write_text(path.read_text().replace(" // x-release-please-version", ""))
                before = tree_bytes(root)
                result = run_script(root, "sync-release-please-config.py")
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(tree_bytes(root), before)

    def test_malformed_ui_prevents_partial_backend_and_manifest_writes(self) -> None:
        write_marked_versions(self.root)
        self.assertEqual(self.sync().returncode, 0)
        set_component_versions(self.root, backend="0.1.2")
        path = self.root / UI_VERSION
        path.write_text(path.read_text().replace(" // x-release-please-version", ""))
        before = tree_bytes(self.root)
        result = self.sync()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(tree_bytes(self.root), before)


if __name__ == "__main__":
    unittest.main()
