from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/release-chart.sh"
DIGEST = "sha256:" + "e" * 64


class ReleaseChartTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.chart = self.root / "charts/example"
        self.chart.mkdir(parents=True)
        (self.chart / "Chart.yaml").write_text("apiVersion: v2\nname: example\nversion: 0.1.0\n")
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.log = self.root / "calls.log"
        self.state = self.root / "state"
        self.package = self.root / "package.tgz"
        crane = self.bin / "crane"
        crane.write_text("#!/usr/bin/env bash\nif [[ -f \"$STATE\" ]]; then cat \"$STATE\"; else exit 1; fi\n")
        helm = self.bin / "helm"
        helm.write_text("""#!/usr/bin/env bash
set -e
echo helm \"$@\" >> \"$CALL_LOG\"
case \"$1\" in
  package)
    mkdir -p \"$4\"
    cp \"$PACKAGE_SOURCE\" \"$4/example-0.1.0.tgz\"
    ;;
  push)
    printf '%s' \"$FAKE_DIGEST\" > \"$STATE\"
    ;;
  pull)
    dest=""
    while [[ $# -gt 0 ]]; do if [[ \"$1\" == --destination ]]; then dest=$2; shift 2; else shift; fi; done
    mkdir -p \"$dest\"
    if [[ -n \"$TAMPER\" ]]; then echo tampered > \"$dest/example-0.1.0.tgz\"; else cp \"$PACKAGE_SOURCE\" \"$dest/example-0.1.0.tgz\"; fi
    ;;
esac
""")
        crane.chmod(0o755)
        helm.chmod(0o755)
        self.package.write_text("deterministic chart package")
        self.env = {**os.environ, "PATH": str(self.bin) + ":" + os.environ["PATH"], "CALL_LOG": str(self.log), "STATE": str(self.state), "FAKE_DIGEST": DIGEST, "PACKAGE_SOURCE": str(self.package), "TAMPER": "", "HIROBA_PYTHON": str(ROOT / ".venv/bin/python")}

    def tearDown(self) -> None:
        self.temp.cleanup()

    def run_chart(self, repair: bool = False, channel: str = "") -> subprocess.CompletedProcess[str]:
        args = ["bash", str(SCRIPT), "--root", str(self.root), "--chart", "example", "--version", "0.1.0", "--repository-base", "ghcr.io/7k-hiroba/app/charts", "--source-sha", "f" * 40, "--output", str(self.root / "artifact.json"), "--channel", channel]
        if repair:
            args += ["--repair", "true"]
        return subprocess.run(args, env=self.env, text=True, capture_output=True, check=False)

    def test_pushes_chart_and_records_digest(self) -> None:
        result = self.run_chart()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        artifact = json.loads((self.root / "artifact.json").read_text())
        self.assertEqual(artifact["digest"], DIGEST)
        self.assertIn("helm push", self.log.read_text())

    def test_existing_identical_chart_is_reused(self) -> None:
        self.state.write_text(DIGEST)
        result = self.run_chart()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("helm push", self.log.read_text())

    def test_existing_tampered_chart_fails(self) -> None:
        self.state.write_text(DIGEST)
        self.env["TAMPER"] = "yes"
        result = self.run_chart()
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("helm push", self.log.read_text())

    def test_edge_channel_is_recorded_without_changing_immutable_version(self) -> None:
        result = self.run_chart(channel="edge")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        artifact = json.loads((self.root / "artifact.json").read_text())
        self.assertEqual(artifact["channel"], "edge")
        self.assertEqual(artifact["tag"], "example-v0.1.0")

    def test_repair_requires_existing_tag_at_current_source(self) -> None:
        result = self.run_chart(repair=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("tag", (result.stdout + result.stderr).lower())
        self.assertFalse(self.state.exists())


if __name__ == "__main__":
    unittest.main()
