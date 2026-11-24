from __future__ import annotations

import hashlib
import json
import os
import tarfile
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
FIXTURE_ROOT = ROOT / "tests/fixtures/non-plugin-runtime"
CHART = FIXTURE_ROOT / "charts/hiroba-nonplugin-smoke"
FIXTURE = FIXTURE_ROOT / "tests/chart-lifecycle/hiroba-nonplugin-smoke"


class ChartLifecycleFixtureTests(unittest.TestCase):
    def package_metadata(self, path: Path) -> dict:
        with tarfile.open(path, "r:gz") as archive:
            for member in archive.getmembers():
                if member.name.count("/") == 1 and member.name.endswith("/Chart.yaml"):
                    source = archive.extractfile(member)
                    self.assertIsNotNone(source)
                    return yaml.safe_load(source.read())
        self.fail(f"Chart.yaml missing from {path}")

    def test_reviewed_fixture_archives_have_exact_provenance_and_distinct_content(self) -> None:
        provenance = json.loads((FIXTURE / "provenance.json").read_text())
        self.assertEqual(provenance["schema"], "inari.chart-lifecycle-fixture-provenance.v1")
        pins = json.loads((ROOT / "pins/stack-testing.json").read_text())
        self.assertEqual(provenance["generator"]["helmVersion"], pins["tools"]["helm"]["version"])
        self.assertEqual(provenance["generator"]["helmArchiveSha256"], pins["tools"]["helm"]["sha256"])
        declaration = yaml.safe_load((CHART / "ci/test.yaml").read_text())
        self.assertEqual(Path(declaration["upgrade"]["previousPackage"]).is_absolute(), False)
        for package in provenance["packages"]:
            archive = FIXTURE / package["file"]
            expected = "sha256:" + hashlib.sha256(archive.read_bytes()).hexdigest()
            self.assertEqual(package["sha256"], expected)
            metadata = self.package_metadata(archive)
            self.assertEqual(metadata["name"], "hiroba-nonplugin-smoke")
            self.assertEqual(str(metadata["version"]), package["chartVersion"])
            self.assertFalse((CHART / package["file"]).exists())
        previous, current = provenance["packages"]
        self.assertEqual([previous["phase"], current["phase"]], ["install", "upgrade"])
        self.assertNotEqual(previous["chartVersion"], current["chartVersion"])
        self.assertNotEqual(previous["sha256"], current["sha256"])
        self.assertEqual(previous["source"], "tests/chart-lifecycle/hiroba-nonplugin-smoke/previous-chart")
        self.assertEqual(current["source"], "charts/hiroba-nonplugin-smoke")
        self.assertTrue(os.access(FIXTURE / "assert.sh", os.X_OK))


if __name__ == "__main__":
    unittest.main()
