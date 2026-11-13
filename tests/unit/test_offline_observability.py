from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/test-offline-observability.sh"


class OfflineObservabilityTests(unittest.TestCase):
    def test_uses_only_offline_gcx_alloy_and_promtool_commands(self) -> None:
        text = SCRIPT.read_text()
        for expected in ("gcx dev lint run", "alloy fmt --test", "alloy validate", "--stability.level generally-available", "--feature.community-components.enabled=false", "promtool test rules"):
            self.assertIn(expected, text)
        self.assertNotIn("gcx resources validate", text)
        self.assertNotIn("docker ", text)
        self.assertIn("files_scanned", text)
        self.assertIn("dashboard.grafana.app/v1beta1", text)
        self.assertIn("No violations found", text)
        self.assertIn("file linted", text)
        self.assertNotIn("docker\n", text)

    def test_requires_reviewed_versioned_post_alloy_fixture(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "scaffold"
            shutil.copytree(ROOT / "scaffold", root, ignore=shutil.ignore_patterns("node_modules", "dist"))
            fixture = root / "observability/tests/alloy/expected-central-series.json"
            data = json.loads(fixture.read_text())
            data.pop("fixtureVersion", None)
            fixture.write_text(json.dumps(data))
            result = subprocess.run(["bash", str(SCRIPT), "--root", str(root)], text=True, capture_output=True, check=False, env={**os.environ, "HIROBA_PYTHON": str(ROOT / ".venv/bin/python")})
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("fixtureVersion", result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
