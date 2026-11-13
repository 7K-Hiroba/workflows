#!/usr/bin/env python3
"""Derive promtool input series from observed post-Alloy labels."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import yaml

SERIES = re.compile(r"^([a-zA-Z_:][a-zA-Z0-9_:]*)(?:\{(.*)\})?$")
LABEL = re.compile(r"([a-zA-Z_][a-zA-Z0-9_]*)=\"([^\"]*)\"")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--actual", type=Path, required=True)
    parser.add_argument("--rules", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    base = yaml.safe_load(args.base.read_text(encoding="utf-8"))
    actual = json.loads(args.actual.read_text(encoding="utf-8"))
    labels = actual.get("labels")
    if not isinstance(labels, dict) or not labels:
        print("::error::actual Alloy result has no labels", file=sys.stderr)
        return 1
    for test in base.get("tests", []):
        for series in test.get("input_series", []):
            match = SERIES.fullmatch(series.get("series", ""))
            if not match:
                print(f"::error::invalid input series: {series.get('series')}", file=sys.stderr)
                return 1
            merged = dict(LABEL.findall(match.group(2) or ""))
            merged.update(labels)
            label_text = ",".join(f'{key}={json.dumps(str(value))}' for key, value in sorted(merged.items()))
            series["series"] = f"{match.group(1)}{{{label_text}}}"
        for alert_test in test.get("alert_rule_test", []):
            for alert in alert_test.get("exp_alerts", []):
                alert.setdefault("exp_labels", {}).update(labels)
    base["rule_files"] = [str(args.rules.resolve())]
    args.output.write_text(yaml.safe_dump(base, sort_keys=False), encoding="utf-8")
    print(f"derived central rule fixture: {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
