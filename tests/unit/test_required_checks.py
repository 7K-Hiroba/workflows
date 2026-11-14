from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/check-required-checks.py"
REQUIRED = ("library-ci-result", "scaffold-ci-result")


class RequiredCheckTests(unittest.TestCase):
    def check(self, lines: list[str]) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "checks.ndjson"
            path.write_text("\n".join(lines) + ("\n" if lines else ""))
            args = ["python3", str(SCRIPT), "--input", str(path)]
            for name in REQUIRED:
                args += ["--required", name]
            return subprocess.run(args, text=True, capture_output=True, check=False)

    def test_exact_completed_success_contexts_pass(self) -> None:
        result = self.check([
            '{"name":"library-ci-result","status":"completed","conclusion":"success"}',
            '{"name":"scaffold-ci-result","status":"completed","conclusion":"success"}',
        ])
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_empty_missing_pending_skipped_and_failed_checks_block(self) -> None:
        cases = (
            [],
            ['{"name":"library-ci-result","status":"completed","conclusion":"success"}'],
            ['{"name":"library-ci-result","status":"completed","conclusion":"success"}', '{"name":"scaffold-ci-result","status":"in_progress","conclusion":null}'],
            ['{"name":"library-ci-result","status":"completed","conclusion":"success"}', '{"name":"scaffold-ci-result","status":"completed","conclusion":"skipped"}'],
            ['{"name":"library-ci-result","status":"completed","conclusion":"failure"}', '{"name":"scaffold-ci-result","status":"completed","conclusion":"success"}'],
        )
        for lines in cases:
            with self.subTest(lines=lines):
                self.assertNotEqual(self.check(lines).returncode, 0)


if __name__ == "__main__":
    unittest.main()
