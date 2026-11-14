from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "check-workflow-pins.py"
SHA = "0123456789abcdef0123456789abcdef01234567"


class WorkflowPinTests(unittest.TestCase):
    def run_checker(self, text: str, *args: str, name: str = "ci.yml") -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            workflow = root / ".github" / "workflows" / name
            workflow.parent.mkdir(parents=True)
            workflow.write_text(text)
            return subprocess.run(
                ["python3", str(SCRIPT), "--root", str(root), *args],
                text=True,
                capture_output=True,
                check=False,
            )

    def test_accepts_full_sha_with_version_and_same_commit_calls(self) -> None:
        result = self.run_checker(
            f"""on: pull_request
jobs:
  test:
    uses: 7K-Hiroba/workflows/.github/workflows/test.yml@{SHA} # v1.0.0
  local:
    uses: $/.github/workflows/local.yml
  steps:
    - uses: actions/checkout@{SHA} # v7.0.0
    - uses: ./.github/actions/local
"""
        )
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)

    def test_rejects_mutable_and_short_refs(self) -> None:
        for ref in ("main", "v1", "0123456789abcdef"):
            with self.subTest(ref=ref):
                result = self.run_checker(f"steps:\n  - uses: actions/checkout@{ref} # v7.0.0\n")
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("full 40-character commit SHA", result.stdout + result.stderr)

    def test_requires_human_readable_version_comment(self) -> None:
        result = self.run_checker(f"steps:\n  - uses: actions/checkout@{SHA}\n")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("version comment", result.stdout + result.stderr)

    def test_rejects_pull_request_target_and_secrets_inherit(self) -> None:
        for token in ("pull_request_target:", "secrets: inherit"):
            with self.subTest(token=token):
                result = self.run_checker(token + "\n")
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("forbidden", result.stdout + result.stderr)

    def test_scaffold_placeholder_only_allowed_in_templates(self) -> None:
        text = "jobs:\n  ci:\n    uses: 7K-Hiroba/workflows/.github/workflows/ci.yml@__WORKFLOWS_V1_SHA__ # v1.0.0\n"
        allowed = self.run_checker(text, name="ci.yml.template")
        self.assertEqual(allowed.returncode, 0, allowed.stdout + allowed.stderr)
        rejected = self.run_checker(text, "--require-rendered", name="ci.yml.template")
        self.assertNotEqual(rejected.returncode, 0)
        outside = self.run_checker(text, name="ci.yml")
        self.assertNotEqual(outside.returncode, 0)


if __name__ == "__main__":
    unittest.main()
