from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "scripts/run-stack-lifecycle.sh"


class StackLifecycleScriptTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.base = Path(self.temporary.name)
        self.root = self.base / "consumer"
        self.fake_bin = self.base / "bin"
        self.fake_bin.mkdir(parents=True)
        self.log = self.base / "commands.log"
        self.make_repo()
        self.make_fake_commands()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def write(self, relative: str, content: str, executable: bool = False) -> None:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        if executable:
            path.chmod(0o755)

    def make_repo(self) -> None:
        self.write(".hiroba.yaml", """schema: inari.hiroba.app.v2
app: example
archetype: stack
trustTier: experimental
components: {chartsRoot: charts, packagesRoot: packages, templatesRoot: templates}
stackTest: {path: tests/stack}
""")
        self.write("tests/stack/suite.yaml", """schema: inari.stack-test.v1
setupProfiles: []
covers: []
fixtureOnly: true
install: {script: install.sh, timeout: 5m}
upgrade: {script: upgrade.sh, timeout: 5m}
diagnostics: diagnostics.sh
""")
        phase = """#!/usr/bin/env bash
set -euo pipefail
printf '%s:%s\n' "$HIROBA_STACK_PHASE" "$HIROBA_STACK_CLUSTER" >> "$STACK_LOG"
if [[ "${SKIP_RESULT:-false}" == true ]]; then exit 0; fi
value=$HIROBA_STACK_PHASE
if [[ "${SAME_DIGEST:-false}" == true ]]; then value=install; fi
digest=$(printf '%s' "$value" | sha256sum | awk '{print $1}')
cat > "$HIROBA_STACK_WORK/$HIROBA_STACK_PHASE-result.json" <<EOF
{"schema":"inari.stack-phase-result.v1","phase":"$HIROBA_STACK_PHASE","version":"$HIROBA_STACK_PHASE","contentDigest":"sha256:$digest","converged":true}
EOF
"""
        self.write("tests/stack/install.sh", phase, executable=True)
        self.write("tests/stack/upgrade.sh", phase, executable=True)
        self.write("tests/stack/diagnostics.sh", "#!/usr/bin/env bash\nprintf 'diagnostics\\n' >> \"$STACK_LOG\"\n", executable=True)
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        subprocess.run(["git", "-C", str(self.root), "config", "user.email", "tests@example.com"], check=True)
        subprocess.run(["git", "-C", str(self.root), "config", "user.name", "Tests"], check=True)
        subprocess.run(["git", "-C", str(self.root), "add", ".hiroba.yaml", "tests/stack"], check=True)
        subprocess.run(["git", "-C", str(self.root), "commit", "-qm", "fixture"], check=True)
        self.source_sha = subprocess.check_output(["git", "-C", str(self.root), "rev-parse", "HEAD"], text=True).strip()

    def make_fake_commands(self) -> None:
        for name in ("kind", "kubectl"):
            path = self.fake_bin / name
            path.write_text(
                "#!/usr/bin/env bash\nprintf '%s:%s\\n' \"" + name + "\" \"$*\" >> \"$STACK_LOG\"\n"
                "if [[ \"${FAIL_KIND_CREATE:-false}\" == true && \"$1\" == create ]]; then exit 1; fi\n",
                encoding="utf-8",
            )
            path.chmod(0o755)

    def run_runner(self, **extra: str) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env.update({
            "PATH": str(self.fake_bin) + os.pathsep + env["PATH"],
            "STACK_LOG": str(self.log),
            "GITHUB_RUN_ID": "123",
            "GITHUB_RUN_ATTEMPT": "1",
            "WORKFLOW_SHA": "a" * 40,
            "HIROBA_PYTHON": str(ROOT / ".venv/bin/python"),
        })
        env.update(extra)
        return subprocess.run(["bash", str(RUNNER), "--root", str(self.root)], text=True, capture_output=True, check=False, env=env, timeout=30)

    def evidence(self) -> dict:
        return json.loads((self.root / "evidence/stack-lifecycle.json").read_text())

    def test_one_cluster_install_then_upgrade_and_source_bound_evidence(self) -> None:
        result = self.run_runner()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        commands = self.log.read_text().splitlines()
        self.assertEqual(1, sum(line.startswith("kind:create cluster") for line in commands))
        self.assertEqual(1, sum(line.startswith("kind:delete cluster") for line in commands))
        install = next(index for index, line in enumerate(commands) if line.startswith("install:"))
        upgrade = next(index for index, line in enumerate(commands) if line.startswith("upgrade:"))
        self.assertLess(install, upgrade)
        self.assertEqual(commands[install].split(":", 1)[1], commands[upgrade].split(":", 1)[1])
        evidence = self.evidence()
        self.assertEqual(evidence["status"], "passed")
        self.assertEqual(evidence["sourceSha"], self.source_sha)
        self.assertEqual(evidence["clusterCreateCount"], 1)
        self.assertEqual(evidence["clusterDeleteCount"], 1)
        self.assertTrue(evidence["freshState"])
        self.assertFalse(evidence["functionalE2E"])
        self.assertEqual(evidence["deployedReadiness"], "not-tested")
        self.assertEqual([phase["phase"] for phase in evidence["phases"]], ["install", "upgrade"])

    def test_missing_phase_result_fails_and_still_cleans_up(self) -> None:
        result = self.run_runner(SKIP_RESULT="true")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("result", result.stdout + result.stderr)
        self.assertEqual(self.evidence()["status"], "failed")
        self.assertEqual(1, sum(line.startswith("kind:delete cluster") for line in self.log.read_text().splitlines()))

    def test_equal_install_and_upgrade_content_fails(self) -> None:
        result = self.run_runner(SAME_DIGEST="true")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("distinct", result.stdout + result.stderr)
        self.assertEqual(self.evidence()["status"], "failed")

    def test_failed_create_still_deletes_a_partial_cluster(self) -> None:
        result = self.run_runner(FAIL_KIND_CREATE="true")
        self.assertNotEqual(result.returncode, 0)
        commands = self.log.read_text().splitlines()
        self.assertEqual(1, sum(line.startswith("kind:delete cluster") for line in commands))
        evidence = self.evidence()
        self.assertEqual(evidence["status"], "failed")
        self.assertEqual(evidence["clusterCreateCount"], 0)
        self.assertEqual(evidence["clusterDeleteCount"], 1)
        self.assertTrue(evidence["cleanedUp"])

    def test_chart_runner_marks_create_attempt_before_kind(self) -> None:
        script = (ROOT / "scripts/run-chart-tests.sh").read_text()
        attempt = script.index("CLUSTER_CREATE_ATTEMPTED=true")
        create = script.index('create_kind_cluster "$CLUSTER"', attempt)
        self.assertLess(attempt, create)
        self.assertIn('if [[ "$CLUSTER_CREATE_ATTEMPTED" == true ]]; then kind delete cluster', script)

    def test_kro_install_reuses_the_verified_digest(self) -> None:
        script = (ROOT / "scripts/lib/stack-cluster.sh").read_text()
        self.assertIn('helm upgrade --install kro "oci://$repository@$expected"', script)
        self.assertNotIn('--version "$version"', script)

    def test_workflow_and_installer_use_exact_cache_and_read_only_permissions(self) -> None:
        workflow_path = ROOT / ".github/workflows/test-stack.yml"
        self.assertTrue(workflow_path.is_file())
        workflow = yaml.safe_load(workflow_path.read_text())
        self.assertEqual(workflow["permissions"], {"contents": "read"})
        self.assertEqual(workflow["jobs"]["test"]["timeout-minutes"], 45)
        text = workflow_path.read_text()
        self.assertIn("actions/cache@", text)
        self.assertNotIn("restore-keys", text)
        self.assertNotIn("id-token: write", text)
        self.assertIn("stack-lifecycle-evidence", text)
        installer = (ROOT / "scripts/install-ci-tools.sh").read_text()
        self.assertIn("pins/stack-testing.json", installer)
        self.assertIn("HIROBA_CACHE_DIR", installer)
        self.assertNotIn("go install", installer)


if __name__ == "__main__":
    unittest.main()
