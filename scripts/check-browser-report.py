#!/usr/bin/env python3
"""Require a passing Playwright test for every declared extension slot."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--extension", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    try:
        extension = yaml.safe_load(args.extension.read_text(encoding="utf-8"))
        required = {f"slot {slot['kind']}:{slot['name']}" for slot in extension["spec"]["ui"]["slots"]}
        report = json.loads(args.report.read_text(encoding="utf-8"))
        passing = set()
        def walk(suites):
            for suite in suites:
                for spec in suite.get("specs", []):
                    if spec.get("ok") and spec.get("title") in required:
                        passing.add(spec["title"])
                walk(suite.get("suites", []))
        walk(report.get("suites", []))
        missing = sorted(required - passing)
        if missing:
            raise ValueError(f"missing passing browser slot tests: {missing}")
    except (OSError, ValueError, KeyError, TypeError, yaml.YAMLError, json.JSONDecodeError) as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 1
    print(f"browser coverage passed for {len(required)} declared slot(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
