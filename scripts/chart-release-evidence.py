#!/usr/bin/env python3
"""Derive chart-release evidence requirements from exact consumer source."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import jsonschema
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.stack_testing import load_stack_plan  # noqa: E402

LANE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--standalone", choices=("true", "false"), required=True)
    parser.add_argument("--required-lanes", required=True)
    args = parser.parse_args()
    try:
        lanes = args.required_lanes.split()
        if not lanes or any(not LANE.fullmatch(lane) for lane in lanes):
            raise ValueError("required lanes must be non-empty valid lane names")
        stack = load_stack_plan(args.root)
        has_stack = bool(stack["enabled"])
        if args.standalone == "true" and has_stack and "stack-lifecycle" not in lanes:
            lanes.append("stack-lifecycle")
        output = {"hasStackTest": has_stack, "requiredLanes": " ".join(lanes)}
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError, yaml.YAMLError, jsonschema.SchemaError) as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 1
    print(json.dumps(output, separators=(",", ":"), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
