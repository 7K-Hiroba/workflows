from __future__ import annotations

import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "run-runtime-smoke.sh"


class RuntimeSmokeScriptTests(unittest.TestCase):
    def run_script(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(["bash", str(SCRIPT), "--root", str(ROOT / "scaffold"), *args], text=True, capture_output=True, check=False)

    def test_rejects_real_environment_profiles_before_cluster_creation(self) -> None:
        for profile in ("stage", "prod"):
            with self.subTest(profile=profile):
                result = self.run_script("--mode", "local", "--profile", profile)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("profile=ci", result.stdout + result.stderr)

    def test_oci_mode_requires_exact_app_and_suite_digests(self) -> None:
        result = self.run_script("--mode", "oci", "--profile", "ci")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("digest", (result.stdout + result.stderr).lower())

    def test_driver_has_argo_lint_diagnostics_and_guaranteed_kind_cleanup(self) -> None:
        text = SCRIPT.read_text()
        for expected in ("argo lint", "argo get", "kind delete cluster", "trap ", "kubectl get events"):
            self.assertIn(expected, text)

    def test_argo_manifest_uses_server_side_create_without_apply_annotation(self) -> None:
        text = SCRIPT.read_text()
        self.assertIn('kubectl create -n argo -f "https://raw.githubusercontent.com/argoproj/argo-workflows/', text)
        self.assertNotIn('kubectl apply -n argo -f "https://raw.githubusercontent.com/argoproj/argo-workflows/', text)

    def test_argo_wait_uses_external_suite_timeout(self) -> None:
        text = SCRIPT.read_text()
        self.assertIn('timeout "$TIMEOUT" argo wait "$WORKFLOW_NAME"', text)
        self.assertNotIn('argo wait "$WORKFLOW_NAME" --namespace default --timeout', text)


if __name__ == "__main__":
    unittest.main()
