from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
PYTHON = ROOT / ".venv" / "bin" / "python"
if not PYTHON.exists():
    PYTHON = Path("python3")


class DeriveCentralFixtureTests(unittest.TestCase):
    def test_derives_reviewed_post_alloy_labels_without_mutating_base_test(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = root / "base.yaml"
            base.write_text("rule_files: [rules/app.yaml]\ntests:\n  - input_series:\n      - series: 'workflows_scaffold_up{job=\"workflows-scaffold\"}'\n    alert_rule_test:\n      - exp_alerts:\n          - exp_labels: {job: workflows-scaffold}\n")
            actual = root / "actual.json"
            actual.write_text(json.dumps({"labels": {"cluster": "kind-ci", "job": "workflows-scaffold", "org": "ci"}, "value": 1}))
            output = root / "derived.yaml"
            result = subprocess.run([str(PYTHON), str(ROOT / "scripts/derive-central-rule-test.py"), "--base", str(base), "--actual", str(actual), "--rules", str(root / "rules/app.yaml"), "--output", str(output)], text=True, capture_output=True, check=False)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            derived = yaml.safe_load(output.read_text())
            series = derived["tests"][0]["input_series"][0]["series"]
            self.assertIn('org="ci"', series)
            self.assertIn('cluster="kind-ci"', series)
            self.assertEqual(derived["rule_files"], [str(root / "rules/app.yaml")])
            self.assertEqual(derived["tests"][0]["alert_rule_test"][0]["exp_alerts"][0]["exp_labels"]["org"], "ci")
            self.assertIn("rules/app.yaml", base.read_text())


if __name__ == "__main__":
    unittest.main()
