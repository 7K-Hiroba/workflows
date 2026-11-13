from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml

from tests.unit.test_validate_repository import make_valid_repo

ROOT = Path(__file__).resolve().parents[2]
PYTHON = ROOT / ".venv" / "bin" / "python"
if not PYTHON.exists():
    PYTHON = Path("python3")


class ReleaseMetadataTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        make_valid_repo(self.root)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def run_script(self, name: str, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [str(PYTHON), str(ROOT / "scripts" / name), "--root", str(self.root), *args],
            text=True,
            capture_output=True,
            check=False,
        )

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

    def test_discovery_can_filter_changed_files(self) -> None:
        changed = self.root / "changed.txt"
        changed.write_text("packages/app/package.yaml\n")
        result = self.run_script("discover-components.py", "--changed-files", str(changed))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        components = json.loads(result.stdout)["components"]
        self.assertEqual(len(components), 1)
        self.assertEqual(components[0]["name"], "app")

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

    def test_release_please_config_covers_every_component(self) -> None:
        result = self.run_script("sync-release-please-config.py")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        config = json.loads((self.root / "release-please-config.json").read_text())
        expected = {"extension", "ui", "charts/workflows-scaffold", "packages/admission-example", "packages/app", "packages/observability-pack", "templates/service"}
        self.assertEqual(set(config["packages"]), expected)
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


if __name__ == "__main__":
    unittest.main()
