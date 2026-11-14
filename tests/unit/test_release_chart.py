from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml

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
        crane.write_text("""#!/usr/bin/env bash
set -e
case "$1" in
  auth)
    [[ "$2" == login ]] || { echo "unsupported crane auth command" >&2; exit 1; }
    echo crane auth login ghcr.io -u "$5" -p '[masked]' >> "$CALL_LOG"
    echo "fake credential output: $7"
    ;;
  login)
    echo "unknown command login for crane" >&2
    exit 1
    ;;
  digest)
    echo crane digest "$2" >> "$CALL_LOG"
    if ! tail -n 2 "$CALL_LOG" | head -n 1 | grep -q '^crane auth login ghcr.io '; then
      echo "unauthenticated crane digest" >&2
      exit 1
    fi
    if [[ -f "$STATE" ]]; then cat "$STATE"; else exit 1; fi
    ;;
esac
""")
        helm = self.bin / "helm"
        helm.write_text("""#!/usr/bin/env bash
set -e
echo helm \"$@\" >> \"$CALL_LOG\"
case \"$1\" in
  package)
    mkdir -p \"$4\"
    version=$($HIROBA_PYTHON -c 'import sys,yaml; print(yaml.safe_load(open(sys.argv[1]))["version"])' \"$2/Chart.yaml\")
    if [[ -n \"$CHART_CAPTURE\" ]]; then cp \"$2/Chart.yaml\" \"$CHART_CAPTURE\"; fi
    printf '%s' \"$version\" > \"$CHART_VERSION_STATE\"
    cp \"$PACKAGE_SOURCE\" \"$4/example-$version.tgz\"
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
        oras = self.bin / "oras"
        oras.write_text("""#!/usr/bin/env bash
set -e
echo oras \"$@\" >> \"$CALL_LOG\"
if [[ \"$1\" == pull ]]; then
  dest=\"\"
  while [[ $# -gt 0 ]]; do if [[ \"$1\" == --output ]]; then dest=$2; shift 2; else shift; fi; done
  mkdir -p \"$dest\"
  version=$(cat \"$CHART_VERSION_STATE\")
  if [[ -n \"$TAMPER\" ]]; then echo tampered > \"$dest/example-$version.tgz\"; else cp \"$PACKAGE_SOURCE\" \"$dest/example-$version.tgz\"; fi
fi
""")
        crane.chmod(0o755)
        helm.chmod(0o755)
        oras.chmod(0o755)
        self.package.write_text("deterministic chart package")
        self.env = {
            **os.environ,
            "PATH": str(self.bin) + ":" + os.environ["PATH"],
            "CALL_LOG": str(self.log),
            "STATE": str(self.state),
            "FAKE_DIGEST": DIGEST,
            "PACKAGE_SOURCE": str(self.package),
            "TAMPER": "",
            "CHART_CAPTURE": "",
            "CHART_VERSION_STATE": str(self.root / "chart-version"),
            "HIROBA_PYTHON": str(ROOT / ".venv/bin/python"),
            "GHCR_ACTOR": "octocat",
            "GHCR_TOKEN": "secret-token",
        }

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
        calls = self.log.read_text()
        self.assertIn("helm push", calls)
        self.assertIn(f"ghcr.io/7k-hiroba/app/charts/example@{DIGEST}", calls)

    def test_crane_login_precedes_every_digest_without_token_output(self) -> None:
        result = self.run_chart()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("secret-token", result.stdout + result.stderr)
        calls = self.log.read_text()
        self.assertNotIn("secret-token", calls)
        crane_calls = [line for line in calls.splitlines() if line.startswith("crane ")]
        login = "crane auth login ghcr.io -u octocat -p [masked]"
        digest = "crane digest ghcr.io/7k-hiroba/app/charts/example:0.1.0"
        self.assertEqual(crane_calls, [login, digest, login, digest, login, digest])
        script = SCRIPT.read_text()
        self.assertIn('crane auth login ghcr.io -u "$GHCR_ACTOR" -p "$GHCR_TOKEN"', script)
        self.assertNotIn("crane login ghcr.io", script)

        workflow = yaml.safe_load((ROOT / ".github/workflows/release-chart.yml").read_text())
        publish = next(step for step in workflow["jobs"]["publish"]["steps"] if step.get("id") == "publish")
        self.assertEqual(publish["env"]["GHCR_ACTOR"], "${{ github.actor }}")
        self.assertEqual(publish["env"]["GHCR_TOKEN"], "${{ secrets.GITHUB_TOKEN }}")

    def test_pinned_crane_cli_rejects_legacy_login_offline(self) -> None:
        configured = os.environ.get("HIROBA_CRANE")
        if configured:
            crane = Path(configured)
        else:
            install_env = {**os.environ, "RUNNER_TEMP": str(self.root), "GITHUB_PATH": ""}
            installed = subprocess.run(["bash", str(ROOT / "scripts/install-ci-tools.sh"), "crane"], env=install_env, text=True, capture_output=True, check=False)
            self.assertEqual(installed.returncode, 0, installed.stdout + installed.stderr)
            crane = self.root / "hiroba-bin/crane"
        version = subprocess.run([str(crane), "version"], text=True, capture_output=True, check=False)
        self.assertEqual(version.returncode, 0, version.stdout + version.stderr)
        self.assertEqual(version.stdout.strip(), "v0.20.7")
        supported = subprocess.run([str(crane), "auth", "login", "--help"], text=True, capture_output=True, check=False)
        self.assertEqual(supported.returncode, 0, supported.stdout + supported.stderr)
        self.assertIn("crane auth login [OPTIONS] [SERVER]", supported.stdout)
        legacy = subprocess.run([str(crane), "login", "--help"], text=True, capture_output=True, check=False)
        self.assertNotEqual(legacy.returncode, 0, legacy.stdout + legacy.stderr)
        self.assertIn('unknown command "login"', legacy.stdout + legacy.stderr)

    def test_new_chart_tampered_exact_digest_pull_fails(self) -> None:
        self.env["TAMPER"] = "yes"
        result = self.run_chart()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("helm push", self.log.read_text())
        self.assertIn("oras pull", self.log.read_text())
        self.assertFalse((self.root / "artifact.json").exists())

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
        self.assertEqual(artifact["tag"], "0.1.0")
        self.assertEqual(artifact["releaseTag"], "example-v0.1.0")

    def test_uses_configured_charts_root(self) -> None:
        configured = self.root / "helm/example"
        configured.parent.mkdir()
        self.chart.rename(configured)
        (self.root / ".hiroba.yaml").write_text("components:\n  chartsRoot: helm\n")
        result = self.run_chart()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(f"helm package {configured}", self.log.read_text())

    def test_edge_packages_prerelease_in_temporary_chart_without_source_mutation(self) -> None:
        source_chart = self.chart / "Chart.yaml"
        original = source_chart.read_bytes()
        capture = self.root / "packaged-Chart.yaml"
        self.env["CHART_CAPTURE"] = str(capture)
        result = subprocess.run([
            "bash", str(SCRIPT), "--root", str(self.root), "--chart", "example", "--version", "0.2.0-0123456",
            "--repository-base", "ghcr.io/7k-hiroba/app/charts", "--source-sha", "f" * 40,
            "--output", str(self.root / "artifact.json"), "--channel", "edge",
        ], env=self.env, text=True, capture_output=True, check=False)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(source_chart.read_bytes(), original)
        self.assertIn("version: 0.2.0-0123456", capture.read_text())
        artifact = json.loads((self.root / "artifact.json").read_text())
        self.assertEqual(artifact["tag"], "0.2.0-0123456")
        self.assertEqual(artifact["releaseTag"], "example-v0.2.0-0123456")
        self.assertIn("example-0.2.0-0123456.tgz", self.log.read_text())

    def test_repair_requires_existing_tag_at_current_source(self) -> None:
        result = self.run_chart(repair=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("tag", (result.stdout + result.stderr).lower())
        self.assertFalse(self.state.exists())


if __name__ == "__main__":
    unittest.main()
