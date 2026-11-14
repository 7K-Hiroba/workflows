#!/usr/bin/env python3
"""Fail closed unless exact required check contexts are completed successfully."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="NDJSON check objects from the candidate SHA API")
    parser.add_argument("--required", action="append", required=True)
    args = parser.parse_args()
    try:
        checks: dict[str, dict] = {}
        for line in args.input.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            item = json.loads(line)
            name = item.get("name")
            if not isinstance(name, str) or not name:
                raise ValueError("check run has no name")
            if name in checks:
                raise ValueError(f"ambiguous duplicate check context: {name}")
            checks[name] = item
        if not checks:
            raise ValueError("candidate has no check runs")
        for name, item in checks.items():
            if str(item.get("status", "")).lower() != "completed" or str(item.get("conclusion", "")).lower() != "success":
                raise ValueError(f"check {name} is not completed with success")
        missing = sorted(set(args.required) - set(checks))
        if missing:
            raise ValueError(f"missing required check contexts: {', '.join(missing)}")
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 1
    print(f"required checks completed successfully: {', '.join(args.required)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
