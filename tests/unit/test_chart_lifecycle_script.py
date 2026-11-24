from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from lib.chart_lifecycle import canonicalize_package  # noqa: E402

RUNNER = ROOT / "scripts/run-chart-tests.sh"
REAL_HELM = shutil.which("helm") or "/opt/bin/helm"


class ChartLifecycleScriptTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.base = Path(self.temporary.name)
        self.root = self.base / "consumer"
        self.chart = self.root / "charts/example"
        self.fixture = self.root / "tests/chart-lifecycle/example"
        self.fake_bin = self.base / "bin"
        self.fake_bin.mkdir(parents=True)
        self.log = self.base / "commands.log"
        self.helm_state = self.base / "helm-state"
        self.make_chart()
        self.make_commands()
        self.make_repo()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def write(self, relative: str, content: str, executable: bool = False) -> Path:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        if executable:
            path.chmod(0o755)
        return path

    def package(self, source: Path, destination: Path) -> None:
        destination.mkdir(parents=True, exist_ok=True)
        for path in source.rglob("*"):
            if path.is_file():
                os.utime(path, (0, 0))
        subprocess.run([REAL_HELM, "package", str(source), "--destination", str(destination)], check=True, capture_output=True)
        metadata = yaml.safe_load((source / "Chart.yaml").read_text())
        raw = destination / f"{metadata['name']}-{metadata['version']}.tgz"
        canonical = destination / f"{metadata['name']}-{metadata['version']}.canonical.tgz"
        canonicalize_package(raw, canonical)
        canonical.replace(raw)

    def make_chart(self) -> None:
        self.write("charts/example/Chart.yaml", "apiVersion: v2\nname: example\ndescription: lifecycle fixture\nversion: 0.1.0\n")
        self.write("charts/example/values.yaml", "{}\n")
        self.write("charts/example/ci/kind-values.yaml", "{}\n")
        self.write("charts/example/templates/configmap.yaml", """apiVersion: v1
kind: ConfigMap
metadata:
  name: {{ .Release.Name }}-lifecycle
data:
  phase: current
""")
        self.declaration = {
            "schema": "inari.chart-test.v1",
            "install": {"timeout": "5m", "values": ["charts/example/ci/kind-values.yaml"]},
            "upgrade": {
                "previousPackage": "tests/chart-lifecycle/example/previous.tgz",
                "currentPackage": "tests/chart-lifecycle/example/current.tgz",
                "timeout": "6m",
                "assertions": "tests/chart-lifecycle/example/assert.sh",
            },
        }
        self.write("charts/example/ci/test.yaml", yaml.safe_dump(self.declaration, sort_keys=False))
        self.fixture.mkdir(parents=True, exist_ok=True)
        previous = self.base / "previous-source/example"
        shutil.copytree(self.chart, previous)
        (previous / "Chart.yaml").write_text("apiVersion: v2\nname: example\ndescription: lifecycle fixture\nversion: 0.0.9\n")
        (previous / "templates/configmap.yaml").write_text("""apiVersion: v1
kind: ConfigMap
metadata:
  name: {{ .Release.Name }}-lifecycle
data:
  phase: previous
""")
        self.package(previous, self.fixture)
        self.package(self.chart, self.fixture)
        (self.fixture / "example-0.0.9.tgz").rename(self.fixture / "previous.tgz")
        (self.fixture / "example-0.1.0.tgz").rename(self.fixture / "current.tgz")
        self.write("tests/chart-lifecycle/example/assert.sh", """#!/usr/bin/env bash
set -euo pipefail
printf 'assert:%s:%s:%s:%s\\n' "$HIROBA_CHART_PHASE" "$HIROBA_CHART_CLUSTER" "$HIROBA_CHART_RELEASE" "$HIROBA_CHART_NAMESPACE" >> "$COMMAND_LOG"
if [[ "${FAIL_ASSERT:-}" == "$HIROBA_CHART_PHASE" ]]; then exit 1; fi
if [[ "${TAMPER_CURRENT:-false}" == true && "$HIROBA_CHART_PHASE" == upgrade ]]; then printf tampered >> "$HIROBA_CHART_PACKAGE"; fi
kubectl wait --for=condition=Available deployment/example --namespace "$HIROBA_CHART_NAMESPACE" --timeout=60s
""", executable=True)

    def make_commands(self) -> None:
        kind = self.fake_bin / "kind"
        kind.write_text("""#!/usr/bin/env bash
printf 'kind:%s\\n' "$*" >> "$COMMAND_LOG"
if [[ "$1" == create && "${FAIL_KIND_CREATE:-false}" == true ]]; then exit 1; fi
if [[ "$1" == delete && "${FAIL_KIND_DELETE:-false}" == true ]]; then exit 1; fi
if [[ "$1" == export ]]; then printf 'kind logs\\n'; fi
""")
        kubectl = self.fake_bin / "kubectl"
        kubectl.write_text("""#!/usr/bin/env bash
printf 'kubectl:%s\\n' "$*" >> "$COMMAND_LOG"
if [[ "${FAIL_KUBECTL:-false}" == true ]]; then exit 1; fi
printf 'kubectl diagnostic\\n'
""")
        ct = self.fake_bin / "ct"
        ct.write_text("#!/usr/bin/env bash\nprintf 'ct:%s\\n' \"$*\" >> \"$COMMAND_LOG\"\n")
        helm = self.fake_bin / "helm"
        helm.write_text("""#!/usr/bin/env bash
set -euo pipefail
printf 'helm:%s\\n' "$*" >> "$COMMAND_LOG"
case "$1" in
  show|package) exec "$REAL_HELM" "$@" ;;
  install)
    if [[ "${FAIL_INSTALL:-false}" == true ]]; then exit 1; fi
    printf '0.0.9' > "$FAKE_HELM_STATE-version"
    ;;
  upgrade)
    [[ -f "$FAKE_HELM_STATE-version" ]] || exit 1
    if [[ "${FAIL_UPGRADE:-false}" == true ]]; then exit 1; fi
    printf '0.1.0' > "$FAKE_HELM_STATE-version"
    ;;
  list)
    if [[ ! -f "$FAKE_HELM_STATE-version" ]]; then printf '[]\\n'; exit 0; fi
    version=$(cat "$FAKE_HELM_STATE-version")
    revision=1
    [[ "$version" == 0.1.0 ]] && revision=2
    [[ "${WRONG_REVISION:-false}" == true ]] && revision=9
    printf '[{"name":"example","namespace":"default","revision":"%s","status":"deployed","chart":"example-%s"}]\\n' "$revision" "$version"
    ;;
  status|history|get) printf 'helm diagnostic\\n' ;;
  *) printf 'unexpected helm command: %s\\n' "$*" >&2; exit 2 ;;
esac
""")
        for path in (kind, kubectl, ct, helm):
            path.chmod(0o755)

    def make_repo(self) -> None:
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        subprocess.run(["git", "-C", str(self.root), "config", "user.email", "tests@example.com"], check=True)
        subprocess.run(["git", "-C", str(self.root), "config", "user.name", "Tests"], check=True)
        subprocess.run(["git", "-C", str(self.root), "add", "."], check=True)
        subprocess.run(["git", "-C", str(self.root), "commit", "-qm", "fixture"], check=True)
        self.source_sha = subprocess.check_output(["git", "-C", str(self.root), "rev-parse", "HEAD"], text=True).strip()
        self.event = self.base / "event.json"
        self.pr_head_sha = "c" * 40
        self.event.write_text(json.dumps({"pull_request": {"head": {"sha": self.pr_head_sha}}}))

    def run_runner(self, stack_covered: str = "false", **extra: str) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env.update({
            "PATH": str(self.fake_bin) + os.pathsep + str(ROOT / ".venv/bin") + os.pathsep + env["PATH"],
            "COMMAND_LOG": str(self.log),
            "FAKE_HELM_STATE": str(self.helm_state),
            "REAL_HELM": REAL_HELM,
            "GITHUB_RUN_ID": "123",
            "GITHUB_RUN_ATTEMPT": "1",
            "GITHUB_EVENT_PATH": str(self.event),
            "WORKFLOW_SHA": "b" * 40,
        })
        env.update(extra)
        return subprocess.run(["bash", str(RUNNER), "--root", str(self.root), "--chart", "charts/example", "--stack-covered", stack_covered], text=True, capture_output=True, check=False, env=env, timeout=45)

    def commands(self) -> list[str]:
        return self.log.read_text().splitlines() if self.log.exists() else []

    def evidence(self) -> dict:
        return json.loads((self.root / "evidence/chart-lifecycle-example.json").read_text())

    def test_one_cluster_ordered_upgrade_and_source_bound_evidence(self) -> None:
        result = self.run_runner()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        commands = self.commands()
        self.assertEqual(1, sum(line.startswith("kind:create cluster") for line in commands))
        self.assertEqual(1, sum(line.startswith("kind:delete cluster") for line in commands))
        self.assertFalse(any(line.startswith("ct:install") for line in commands))
        install = next(index for index, line in enumerate(commands) if line.startswith("helm:install example "))
        install_assert = next(index for index, line in enumerate(commands) if line.startswith("assert:install:"))
        upgrade = next(index for index, line in enumerate(commands) if line.startswith("helm:upgrade example "))
        upgrade_assert = next(index for index, line in enumerate(commands) if line.startswith("assert:upgrade:"))
        self.assertLess(install, install_assert)
        self.assertLess(install_assert, upgrade)
        self.assertLess(upgrade, upgrade_assert)
        self.assertNotIn("--install", commands[upgrade])
        self.assertNotIn("--atomic", commands[upgrade])
        self.assertEqual(commands[install_assert].split(":")[2], commands[upgrade_assert].split(":")[2])
        self.assertEqual(commands[install_assert].split(":")[3:], ["example", "default"])
        evidence = self.evidence()
        self.assertEqual(evidence["status"], "passed")
        self.assertEqual(evidence["sourceSha"], self.source_sha)
        self.assertEqual(evidence["prHeadSha"], self.pr_head_sha)
        self.assertEqual(evidence["workflowSha"], "b" * 40)
        self.assertEqual(evidence["clusterCreateCount"], 1)
        self.assertEqual(evidence["clusterDeleteCount"], 1)
        self.assertTrue(evidence["freshState"])
        self.assertTrue(evidence["cleanedUp"])
        self.assertFalse(evidence["fixtureOnly"])
        self.assertEqual(evidence["evidenceScope"], "application")
        self.assertTrue(evidence["appEvidenceEligible"])
        self.assertFalse(evidence["functionalE2E"])
        self.assertEqual(evidence["deployedReadiness"], "not-tested")
        self.assertEqual([phase["phase"] for phase in evidence["phases"]], ["install", "upgrade"])
        self.assertEqual([phase["revision"] for phase in evidence["phases"]], [1, 2])
        self.assertEqual([phase["version"] for phase in evidence["phases"]], ["0.0.9", "0.1.0"])
        digests = [phase["packageDigest"] for phase in evidence["phases"]]
        self.assertNotEqual(digests[0], digests[1])
        for phase, package in zip(evidence["phases"], ("previous.tgz", "current.tgz")):
            expected = hashlib.sha256((self.fixture / package).read_bytes()).hexdigest()
            self.assertEqual(phase["packageDigest"], "sha256:" + expected)
            self.assertTrue(phase["converged"])
            self.assertEqual(phase["assertions"], "passed")

    def test_same_content_or_non_reproducible_current_package_fails_before_kind(self) -> None:
        current = self.fixture / "current.tgz"
        original = current.read_bytes()
        current.write_bytes((self.fixture / "previous.tgz").read_bytes())
        result = self.run_runner()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("version", result.stdout + result.stderr)
        self.assertFalse(any(line.startswith("kind:create") for line in self.commands()))
        current.write_bytes(original)
        with current.open("ab") as stream:
            stream.write(b"unreviewed")
        result = self.run_runner()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(any(line.startswith("kind:create") for line in self.commands()))

    def test_failed_upgrade_records_diagnostics_and_cleans_up(self) -> None:
        result = self.run_runner(FAIL_UPGRADE="true")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(1, sum(line.startswith("kind:delete cluster") for line in self.commands()))
        evidence = self.evidence()
        self.assertEqual(evidence["status"], "failed")
        self.assertEqual([phase["status"] for phase in evidence["phases"]], ["passed", "failed"])
        self.assertIn("helm diagnostic", (self.root / "diagnostics/chart-example.txt").read_text())

    def test_failed_install_never_runs_upgrade_or_hides_phase(self) -> None:
        result = self.run_runner(FAIL_INSTALL="true")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(any(line.startswith("helm:upgrade") for line in self.commands()))
        self.assertEqual([phase["status"] for phase in self.evidence()["phases"]], ["failed", "not-run"])

    def test_failed_assertion_and_convergence_both_clean_up(self) -> None:
        for extra in ({"FAIL_ASSERT": "upgrade"}, {"WRONG_REVISION": "true"}):
            with self.subTest(extra=extra):
                self.log.unlink(missing_ok=True)
                self.helm_state.with_name(self.helm_state.name + "-version").unlink(missing_ok=True)
                result = self.run_runner(**extra)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(1, sum(line.startswith("kind:delete cluster") for line in self.commands()))

    def test_failure_diagnostics_redact_secret_manifest_data(self) -> None:
        helm = self.fake_bin / "helm"
        original = "status|history|get) printf 'helm diagnostic\\n' ;;"
        replacement = """status|history) printf 'helm diagnostic\\n' ;;
  get) cat <<'EOF'
apiVersion: v1
kind: Secret
metadata:
  name: example
data:
  password: c3VwZXItc2VjcmV0
stringData:
  token: plaintext-secret
---
apiVersion: v1
kind: ConfigMap
data:
  visible: retained
EOF
    ;;"""
        helm.write_text(helm.read_text().replace(original, replacement))
        result = self.run_runner(FAIL_ASSERT="upgrade")
        self.assertNotEqual(result.returncode, 0)
        diagnostic = (self.root / "diagnostics/chart-example.txt").read_text()
        self.assertIn("kind: Secret", diagnostic)
        self.assertIn("visible: retained", diagnostic)
        self.assertNotIn("c3VwZXItc2VjcmV0", diagnostic)
        self.assertNotIn("plaintext-secret", diagnostic)

    def test_diagnostics_failure_cannot_abort_cleanup(self) -> None:
        result = self.run_runner(FAIL_ASSERT="upgrade", FAIL_KUBECTL="true")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(1, sum(line.startswith("kind:delete cluster") for line in self.commands()))
        evidence = self.evidence()
        self.assertEqual(evidence["status"], "failed")
        self.assertTrue(evidence["cleanedUp"])

    def test_package_tampering_after_preflight_fails(self) -> None:
        result = self.run_runner(TAMPER_CURRENT="true")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("changed", result.stdout + result.stderr)
        self.assertEqual(self.evidence()["status"], "failed")

    def test_cleanup_and_partial_create_failures_are_failures(self) -> None:
        result = self.run_runner(FAIL_KIND_DELETE="true")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.evidence()["cleanedUp"])
        self.log.unlink(missing_ok=True)
        self.helm_state.with_name(self.helm_state.name + "-version").unlink(missing_ok=True)
        result = self.run_runner(FAIL_KIND_CREATE="true")
        self.assertNotEqual(result.returncode, 0)
        evidence = self.evidence()
        self.assertEqual(evidence["clusterCreateCount"], 0)
        self.assertEqual(evidence["clusterDeleteCount"], 1)

    def test_stack_covered_upgrade_fails_instead_of_skipping(self) -> None:
        result = self.run_runner(stack_covered="true")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("stack-covered", result.stdout + result.stderr)
        self.assertFalse(any(line.startswith("kind:create") for line in self.commands()))

    def test_install_only_chart_retains_ct_install_and_no_lifecycle_evidence(self) -> None:
        del self.declaration["upgrade"]
        self.write("charts/example/ci/test.yaml", yaml.safe_dump(self.declaration, sort_keys=False))
        result = self.run_runner()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(any(line.startswith("ct:install") for line in self.commands()))
        self.assertFalse((self.root / "evidence/chart-lifecycle-example.json").exists())


if __name__ == "__main__":
    unittest.main()
