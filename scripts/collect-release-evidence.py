#!/usr/bin/env python3
"""Normalize trusted workflow results and validate release lane evidence."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.evidence import collect_lanes  # noqa: E402

LANE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
STATUS = {"success": "passed", "failure": "failed", "cancelled": "failed", "skipped": "skipped"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--required-lanes", default="validate")
    parser.add_argument("--lane", action="append", default=[], help="Reusable result as lane=success|failure|cancelled|skipped")
    args = parser.parse_args()
    try:
        args.evidence_dir.mkdir(parents=True, exist_ok=True)
        for item in args.lane:
            name, separator, result = item.partition("=")
            if not separator or not LANE.fullmatch(name) or result not in STATUS:
                raise ValueError(f"invalid reusable lane result: {item!r}")
            document = {"schema": "inari.lane-result.v1", "lane": name, "status": STATUS[result]}
            (args.evidence_dir / f"{name}.json").write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        required = set(args.required_lanes.split())
        if not required or any(not LANE.fullmatch(name) for name in required):
            raise ValueError("required lanes must be non-empty valid lane names")
        lanes = collect_lanes(args.evidence_dir, required, args.source_sha.lower())
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 1
    print(f"release evidence passed: {', '.join(lane['lane'] for lane in lanes)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
